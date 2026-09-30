"""Editable broadcast layouts adapted from the supplied three Qt designs."""
import copy
import io
import zipfile
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageDraw, ImageFilter, ImageChops


def news_frame(size,color,accent,opacity=94):
    """Resolution-independent bevelled broadcast panel with clipped corners."""
    w,h=size
    cut=max(8,round(min(w,h)*.075))
    points=[(cut,0),(w-cut-1,0),(w-1,cut),(w-1,h-cut-1),
            (w-cut-1,h-1),(cut,h-1),(0,h-cut-1),(0,cut)]
    mask=Image.new('L',size,0);ImageDraw.Draw(mask).polygon(points,fill=255)
    panel=Image.new('RGBA',size)
    draw=ImageDraw.Draw(panel)
    for y in range(h):
        light=.65+.30*(1-y/max(1,h-1))
        draw.line((0,y,w,y),fill=tuple(round(v*light) for v in color)+(round(255*opacity/100),))
    draw.line(points+[points[0]],fill=(*accent,255),width=max(3,round(min(w,h)*.026)))
    inset=max(4,round(min(w,h)*.025))
    inner=[(max(inset,min(w-inset-1,x)),max(inset,min(h-inset-1,y))) for x,y in points]
    draw.line(inner+[inner[0]],fill=(3,37,30,255),width=max(2,inset//2))
    draw.line([points[7],points[0],points[1],points[2]],fill=(223,231,197,255),width=max(2,inset//3))
    draw.line([points[3],points[4],points[5]],fill=(24,113,92,255),width=max(2,inset//3))
    panel.putalpha(ImageChops.multiply(panel.getchannel('A'),mask))
    return panel


def news_layout(c,cfg,W,H):
    """Measure wrapped headline copy before allocating the subject's remaining space."""
    width=round(W*.455)
    text=c.apply_text_case(cfg,'headline',cfg.get('headline',''))
    _,size=c.styled_text(cfg,'headline',(255,255,255),round(cfg['headline_font_size']*H/1080))
    modules=c._load_pango_modules()
    if modules:
        cairo,Pango,_=modules
        context=cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32,1,1))
        layout=c._pango_layout(text,c.ShapedFont(c.text_font_family(cfg,'headline',text),size,'bold'),context)
        layout.set_width(max(1,width-round(92*H/1080))*Pango.SCALE)
        layout.set_wrap(Pango.WrapMode.WORD_CHAR)
        requested=layout.get_pixel_size()[1]+round(92*H/1080)
    else:
        font=c.text_font(cfg,'headline',size,'bold')
        draw=ImageDraw.Draw(Image.new('RGB',(1,1)))
        available=max(1,width-round(92*H/1080))
        lines=sum(max(1,int(c.text_bbox(draw,line,font)[0]/available)+1) for line in text.split('\n'))
        requested=round(lines*size*1.3+92*H/1080)
    height=max(round(H*.16),min(round(H*.30),requested))
    if not cfg.get('auto_text_height',True):
        height=round(H*cfg.get('headline_height_pct',16)/100)
    top=round(H*.18);gap=round(H*.024)
    maximum=round(H*.88)-top-height-gap
    if cfg.get('auto_text_height',True):
        value=c.apply_text_case(cfg,'subject',cfg.get('subject',''))
        _,font_size=c.styled_text(cfg,'subject',(255,255,255),round(cfg['subject_font_size']*H/1080))
        if modules:
            body=c._pango_layout(value,c.ShapedFont(c.text_font_family(cfg,'subject',value),font_size,'regular'),context)
            body.set_width(max(1,width-round(92*H/1080))*Pango.SCALE)
            body.set_wrap(Pango.WrapMode.WORD_CHAR)
            needed=body.get_pixel_size()[1]+round(92*H/1080)
        else:
            font=c.text_font(cfg,'subject',font_size,'regular')
            needed=sum(max(1,int(c.text_bbox(draw,line,font)[0]/available)+1) for line in value.split('\n'))*font_size*1.3+92*H/1080
        subject_height=min(maximum,max(round(H*.25),round(needed)))
    else:
        subject_height=min(maximum,round(H*cfg.get('subject_height_pct',40)/100))
    return (round(W*.49),top,width,height),(round(W*.49),top+height+gap,width,subject_height)


def news_text_layer(c,cfg,role,size):
    """Wrap complete shaped paragraphs, then fit inside a clipped text surface."""
    w,h=size
    value=c.apply_text_case(cfg,role,cfg.get(role,''))
    if role=='headline':
        paragraphs=[' '.join(line.split()) for line in value.replace('\\n','\n').splitlines() if line.strip()]
        value='\n'.join(paragraphs[:1]+[' '.join(paragraphs[1:])]) if len(paragraphs)>1 else (paragraphs[0] if paragraphs else '')
    max_lines=cfg.get('_news_max_lines',2)
    background=c.normalize_rgb(cfg.get(role+'_box_color'),(0,60,46))
    layer=Image.new('RGBA',size,(*background,round(255*cfg['box_opacity_pct']/100)))
    if not value.strip():
        return layer
    color,requested=c.styled_text(cfg,role,c.readable_text_colors(background)[0],
                                 round(cfg[role+'_font_size']*cfg['_news_scale']))
    padding=max(1,round(cfg.get('_news_padding',24)*cfg['_news_scale']))
    vertical=cfg.get('_news_vertical_align','center' if role=='headline' else 'top')
    aw,ah=max(1,w-padding*2),max(1,h-padding*2)
    modules=c._load_pango_modules()
    if modules:
        cairo,Pango,PangoCairo=modules
        surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,w,h)
        context=cairo.Context(surface)
        def layout(font_size):
            family=c.text_font_family(cfg,role,value)
            font=c.ShapedFont(family,font_size,'bold' if role=='headline' else 'regular')
            text=c._pango_layout(value,font,context)
            text.set_width(aw*Pango.SCALE)
            text.set_wrap(Pango.WrapMode.WORD_CHAR)
            text.set_alignment({'left':Pango.Alignment.LEFT,'center':Pango.Alignment.CENTER,
                                'right':Pango.Alignment.RIGHT}[cfg[role+'_align']])
            return text
        lo,hi=1,requested
        while lo<hi:
            mid=(lo+hi+1)//2
            ink,logical=layout(mid).get_pixel_extents()
            if max(ink.height,logical.height)<=ah and ink.width<=aw and (role!='headline' or layout(mid).get_line_count()<=max_lines):
                lo=mid
            else:
                hi=mid-1
        text=layout(lo)
        ink,logical=text.get_pixel_extents()
        context.set_source_rgb(*(channel/255 for channel in color))
        y=((h-ink.height)/2 if vertical=='center' else h-padding-ink.height if vertical=='bottom' else padding)-ink.y
        context.move_to(padding,y)
        PangoCairo.show_layout(context,text)
        surface.flush()
        pixels=Image.frombuffer('RGBA',size,bytes(surface.get_data()),'raw','BGRa',0,1)
        layer.alpha_composite(pixels)
        return layer
    if c._needs_shaped_text(value):
        raise RuntimeError('Multilingual text needs the bundled Pango runtime. Run scoreboard setup on the host.')
    draw=ImageDraw.Draw(layer)
    def layout(font_size):
        font=c.text_font(cfg,role,font_size,'bold' if role=='headline' else 'regular')
        lines=[]
        for paragraph in value.split('\n'):
            line=''
            for word in paragraph.split():
                candidate=(line+' '+word).strip()
                if line and c.text_bbox(draw,candidate,font)[0]>aw:
                    lines.append(line);line=word
                else:
                    line=candidate
            lines.append(line)
        text='\n'.join(lines)
        spacing=max(1,round(font_size*.2))
        bounds=draw.multiline_textbbox((0,0),text,font=font,spacing=spacing)
        return font,text,spacing,bounds
    lo,hi=1,requested
    while lo<hi:
        mid=(lo+hi+1)//2
        *_,bb=layout(mid)
        if bb[2]-bb[0]<=aw and bb[3]-bb[1]<=ah and (role!='headline' or len(layout(mid)[1].split('\n'))<=max_lines): lo=mid
        else: hi=mid-1
    font,text,spacing,bb=layout(lo)
    align=cfg[role+'_align']
    x=padding if align=='left' else w-padding-(bb[2]-bb[0]) if align=='right' else (w-bb[2]+bb[0])/2
    text_layer=Image.new('RGBA',size)
    ImageDraw.Draw(text_layer).multiline_text((x-bb[0],padding-bb[1]),text,font=font,fill=(*color,255),spacing=spacing,align=align)
    bounds=text_layer.getchannel('A').getbbox()
    if vertical!='top' and bounds:
        ink=text_layer.crop(bounds)
        y=round((h-ink.height)/2) if vertical=='center' else h-padding-ink.height
        layer.alpha_composite(ink,(bounds[0],y))
    else:
        layer.alpha_composite(text_layer)
    return layer


def render_news(c,image,cfg):
    W,H=image.size
    accent=c.normalize_rgb(cfg.get('accent_color'),(38,199,153))
    def panel(box,color,content=None):
        x,y,w,h=box
        frame=news_frame((w,h),color,accent,cfg['box_opacity_pct'])
        shadow=Image.new('RGBA',(w+24,h+24))
        shadow.paste((0,0,0,150),(12,12,w+12,h+12))
        shadow=shadow.filter(ImageFilter.GaussianBlur(8))
        image.paste(shadow,(x,y),shadow)
        image.paste(frame,(x,y),frame)
        if content is not None:
            inset=max(8,round(22*H/1080))
            content=content.resize((w-inset*2,h-inset*2),Image.Resampling.LANCZOS)
            image.paste(content,(x+inset,y+inset),content)
    image_box=(round(W*.145),round(H*.18),round(W*.315),round(H*.67))
    inset=max(8,round(22*H/1080))
    source=c.load_photo(cfg.get('image_path',''))
    if source and cfg.get('auto_image_frame',True):
        x,y,w,h=image_box
        fit=min((w-2*inset)/source.width,(h-2*inset)/source.height)
        fw=max(inset*2+1,round(source.width*fit)+inset*2)
        fh=max(inset*2+1,round(source.height*fit)+inset*2)
        image_box=(x+(w-fw)//2,y,fw,fh)
    left=Image.new('RGBA',(image_box[2]-2*inset,image_box[3]-2*inset),(0,0,0,0))
    if source:
        scale=min(left.width/source.width,left.height/source.height)*cfg['image_size_pct']/100
        source=source.resize((max(1,round(source.width*scale)),max(1,round(source.height*scale))),Image.Resampling.LANCZOS)
        left.alpha_composite(source,(round(left.width*.5-source.width*.5+W*cfg['image_offset_x_pct']/100),
                                     round(left.height*.5-source.height*.5+H*cfg['image_offset_y_pct']/100)))
    panel(image_box,(3,30,77) if c._competition_theme.active(cfg) else (0,65,49),left)
    for role,box in zip(('headline','subject'),news_layout(c,cfg,W,H)):
        x,y,w,h=box
        layer=news_text_layer(c,dict(cfg,_news_scale=H/1080,box_opacity_pct=0),role,(w-2*inset,h-2*inset))
        panel(box,c.normalize_rgb(cfg.get(role+'_box_color'),(0,65,49)),layer)
    rail=(round(W*.025),round(H*.09),round(W*.085),round(H*.83))
    rail_styles=copy.deepcopy(cfg.get('text_styles',{}))
    rail_styles['headline']=copy.deepcopy(rail_styles.get('rail_text',{}))
    rail_styles['headline']['case']='UPPERCASE'
    rail_value=cfg.get('rail_text','BILLIE JEAN KING CUP 2026')
    if ' '.join(rail_value.upper().split())=='BILLI JEAN KING CUP 2026':
        rail_value='BILLIE JEAN KING CUP 2026'
    rail_cfg=dict(cfg,headline=rail_value,headline_align='center',headline_font_size=cfg.get('rail_font_size',78),text_styles=rail_styles,
                  box_opacity_pct=0,_news_scale=H/1080,_news_max_lines=1)
    text=news_text_layer(c,rail_cfg,'headline',(rail[3]-2*inset,rail[2]-2*inset)).rotate(90,expand=True)
    panel(rail,(3,30,77) if c._competition_theme.active(cfg) else (0,54,42),text)
    if cfg.get('show_logo',True) and (not c._competition_theme.active(cfg) or cfg.get('logo_path')):
        logo=c.load_photo(cfg.get('logo_path') or str(Path(__file__).with_name('match_davis_logo.png')))
        if logo:
            logo.thumbnail((round(W*.23),round(H*.19)),Image.Resampling.LANCZOS)
            image.paste(logo,(round(W*.72-logo.width/2),round(H*.035)),logo)
    return image


def register(namespace):
    c = SimpleNamespace(**namespace)
    root = Path(__file__).parent
    common = dict(canvas_size='HD  (1920x1080)', country_a='India', country_b='Korea',
                  background_path='', logo_path='', background_color=[255,0,255],
                  accent_color=[0,229,117], text_styles={}, rows=[],
                  logo_x_pct=50, logo_y_pct=15, logo_size_pct=15)
    portraits = {f'photo_{side}_{field}':value for side in ('a','b') for field,value in
                 [('offset_x_pct',0),('offset_y_pct',0),('size_pct',100)]}
    defaults = {
        't10':dict(common, title='DAY 1', subtitle='MATCH 1', player_a='', player_b='',
                   photo_a='', photo_b='', **portraits),
        't11':dict(common, title='COMING NEXT', band_x_pct=50, band_y_pct=88, band_size_pct=100,
                   title_box_color=[0,57,36], title_box_opacity_pct=100,
                   transparent_background=True, overlay_opacity_pct=100),
        't12':dict(common, title='QUARTER FINALS 2026', subtitle='Match 1 - Round 2',
                   date_text='', venue='', country_a='Japan', country_b='Spain',
                   logo_y_pct=6.5,logo_size_pct=10),
        't13':dict(canvas_size='HD  (1920x1080)',background_path='',image_path='',logo_path='',show_logo=True,
                   auto_text_height=True,headline_height_pct=16,subject_height_pct=40,auto_image_frame=True,
                   background_color=[0,30,40],accent_color=[38,199,153],text_styles={},rows=[],
                   headline='NEWS HEADLINE',subject='',headline_font_size=68,subject_font_size=42,
                   rail_text='BILLIE JEAN KING CUP 2026',rail_font_size=78,
                   headline_align='center',subject_align='left',headline_box_color=[0,68,52],
                   subject_box_color=[0,68,52],box_opacity_pct=94,
                   image_offset_x_pct=0,image_offset_y_pct=0,image_size_pct=100),
        't15':dict(canvas_size='HD  (1920x1080)',band_path='',band_x_pct=50,band_y_pct=75,
                   band_size_pct=100,overlay_opacity_pct=100,background_color=[0,0,0],
                   accent_color=[0,229,117],text_styles={},rows=[]),
        't16':dict(canvas_size='HD  (1920x1080)',text_a='PLAYER NAME',text_b='COUNTRY / INFORMATION',
                   band_x_pct=50,band_y_pct=82,band_size_pct=100,overlay_opacity_pct=100,
                   green_color=[0,92,57],white_color=[246,247,243],accent_color=[20,205,70],
                   text_a_color=[255,255,255],text_b_color=[0,92,57],
                   background_color=[0,0,0],text_styles={},rows=[]),
        't17':dict(canvas_size='HD  (1920x1080)',text='YOUR TEXT HERE',
                   band_x_pct=50,band_y_pct=90,band_size_pct=90,overlay_opacity_pct=100,
                   green_color=[0,92,57],accent_color=[20,205,70],text_color=[255,255,255],
                   background_color=[0,0,0],text_styles={},rows=[]),
        't18':dict(canvas_size='HD  (1920x1080)',player_a='Sumit Nagal',player_b='Hyeon Chung',
                   country_a='India',country_b='Korea',scores_a=['2','6','5','',''],
                   scores_b=['6','4','6','',''],set_count=3,band_x_pct=50,band_y_pct=82,
                   band_size_pct=100,overlay_opacity_pct=100,top_row_color=[242,242,242],
                   bottom_row_color=[0,103,61],divider_color=[145,145,145],
                   top_text_color=[35,35,35],bottom_text_color=[255,255,255],
                   top_score_color=[35,35,35],bottom_score_color=[255,255,255],
                   background_color=[0,0,0],accent_color=[0,103,61],transparent_background=True,
                   text_styles={},rows=[]),
        't19':dict(common, title='COMING NEXT', versus='VS', player_a='PLAYER 1', player_b='PLAYER 2',
                   background_mode='Transparent', background_color=[12,35,30],
                   photo_a='', photo_b='', **portraits,
                   band_x_pct=50, band_y_pct=80, band_size_pct=100,
                   title_box_color=[0,57,36], title_text_color=[255,255,255],
                   left_panel_color=[0,92,57], right_panel_color=[0,92,57],
                   left_text_color=[255,255,255], right_text_color=[255,255,255],
                   left_country_panel_color=[246,247,243], right_country_panel_color=[246,247,243],
                   left_country_text_color=[0,57,36], right_country_text_color=[0,57,36],
                   versus_panel_color=[0,57,36], versus_text_color=[211,181,92],
                   versus_outline_color=[211,181,92],
                   transparent_background=True, overlay_opacity_pct=100),
    }

    defaults['t20'] = dict(template='t20',canvas_size='HD  (1920x1080)',
        title='QUALIFIERS',date_text='07 - 08 FEBRUARY 2026',
        country_a='Korea',country_b='Argentina',country_a_label='KOREA, REP.',country_b_label='ARGENTINA',
        score_a='3',score_b='2',band_x_pct=50,band_y_pct=84,band_size_pct=100,
        overlay_opacity_pct=100,transparent_background=True,text_styles={},
        background_color=[0,0,0],accent_color=[50,237,189],rows=[],
        title_color=[255,255,255],date_color=[255,255,255],country_color=[3,30,77],
        score_a_color=[50,237,189],score_b_color=[255,255,255],divider_color=[50,237,189])

    defaults['t21'] = dict(template='t21',canvas_size='HD  (1920x1080)',
        country='Belgium',player_1='Hanne Vandewinkel',player_2='Greet Minnen',
        player_3='Jana Otzipka',player_4='Magali Kempen',player_5='Lara Salden',
        panel_style='solid',panel_color=[6,40,106],panel_color_2=[10,67,156],
        panel_text_color=[255,255,255],country_color=[255,255,255],
        border_color=[212,225,255],divider_color=[64,100,159],
        accent_color=[210,255,36],background_color=[3,30,77],background_path='',
        band_x_pct=50,band_y_pct=50,band_size_pct=100,
        panel_width_pct=48,panel_height_pct=88,text_styles={},rows=[])

    defaults['t21']['row_count']=5
    for i in range(6,13):
        defaults['t21']['player_'+str(i)]=''
    defaults['t22']=dict(defaults['t21'],template='t22',country_a='Belgium',country_b='Italy',
        panel_width_pct=88,panel_height_pct=82,
        player_header_a='PLAYER',ranking_header_a='RANKING',player_header_b='PLAYER',ranking_header_b='RANKING')
    for i in range(1,13):
        for side in ('a','b'):
            defaults['t22']['name_'+side+'_'+str(i)]=''
            defaults['t22']['rank_'+side+'_'+str(i)]=''

    defaults['t23']=dict(template='t23',canvas_size='HD  (1920x1080)',
        headline='Vishal Uppal\nPrediction',subject='Semifinalist\n\n1. a\n2. b',
        subject_align='left',subject_vertical_align='center',subject_font_size=72,
        background_color=[3,30,77],accent_color=[210,255,36],text_styles={},rows=[])

    def render_prediction(cfg):
        W,H=c.BROADCAST_SIZES.get(cfg.get('canvas_size'),(1920,1080))
        source=c.load_photo(str(root/'prediction_background_front.png'))
        if source is None:
            raise RuntimeError('Predection artwork is missing: prediction_background_front.png')
        image=source.convert('RGBA').resize((W,H),Image.Resampling.LANCZOS)
        # Coordinates follow the fixed artwork, leaving the bevels and angled ends clear.
        def text(value,role,box,font_size,color):
            x,y,w,h=(round(v*s) for v,s in zip(box,(W/1672,H/941,W/1672,H/941)))
            text_cfg={role:value,role+'_font_size':font_size*1080/941,
                      role+'_align':'left',role+'_box_color':[3,30,77],
                      'text_styles':{role:{'color':color}},
                      'box_opacity_pct':0,'_news_scale':H/1080,'_news_max_lines':1,'_news_padding':8}
            if role=='subject':
                text_cfg['subject_align']=cfg.get('subject_align','left')
                text_cfg['subject_font_size']=cfg.get('subject_font_size',72)
                text_cfg['_news_vertical_align']=cfg.get('subject_vertical_align','center')
            image.alpha_composite(news_text_layer(c,text_cfg,role,(w,h)),(x,y))
        lines=cfg.get('headline','').replace('\\n','\n').split('\n',1)
        if len(lines)==1:
            text(lines[0],'headline',(788,186,714,184),90,[255,255,255])
        else:
            text(lines[0],'headline',(788,183,714,103),90,[255,255,255])
            text(' '.join(lines[1].split()),'headline',(788,277,714,103),90,[210,255,36])
        text(cfg.get('subject',''),'subject',(776,439,752,292),54,[255,255,255])
        return image

    defaults['t24']=dict(template='t24',canvas_size='HD  (1920x1080)',
        match_mode='Singles',partner_a='',partner_b='',
        player_a='CRISTINA BUCSA',player_b='LINDA NOSKOVA',
        day='DAY 1',title='SEMIFINAL',first_name_a='CRISTINA',last_name_a='BUCSA',
        first_name_b='LINDA',last_name_b='NOSKOVA',country_a='Spain',country_b='Czechia',
        country_a_label='',country_b_label='',versus='VS',background_path='',
        background_color=[3,30,77],accent_color=[210,255,36],text_styles={},rows=[])

    def render_semi_finals(cfg):
        W,H=c.BROADCAST_SIZES.get(cfg.get('canvas_size'),(1920,1080))
        source=c.load_photo(cfg.get('background_path') or str(root/'semi_finals_background.png'))
        if source is None:
            raise RuntimeError('Semi Finals background is missing')
        image=source.convert('RGBA').resize((W,H),Image.Resampling.LANCZOS)
        draw=ImageDraw.Draw(image)
        def text(role,value,x,y,width,height,size,variant='bold'):
            value=c.apply_text_case(cfg,role,str(value).replace('\n',' '))
            color,size=c.styled_text(cfg,role,(255,255,255),round(size*H/937))
            factory=c.text_font_factory(cfg,role,variant,value)
            lo,hi=1,size
            while lo<hi:
                mid=(lo+hi+1)//2
                tw,th=c.text_bbox(draw,value,factory(mid))
                if tw<=width*W/1678 and th<=height*H/937:
                    lo=mid
                else:
                    hi=mid-1
            font=factory(lo)
            c.draw_text_centered(draw,value,font,round(x*W/1678),round(y*H/937),color)
        # Render flags at double size for smooth circular edges inside the silver rims.
        for side,cx in (('a',488),('b',1182)):
            code=c.qualifier_country_code(cfg['country_'+side])
            if code:
                with zipfile.ZipFile(root/'country_flags.zip') as archive:
                    flag=Image.open(io.BytesIO(archive.read(code+'.png'))).convert('RGBA')
                diameter=max(2,round(262*H/937))
                flag=flag.resize((diameter*2,diameter*2),Image.Resampling.LANCZOS)
                mask=Image.new('L',flag.size)
                ImageDraw.Draw(mask).ellipse((0,0,flag.width-1,flag.height-1),fill=255)
                flag.putalpha(mask)
                flag=flag.resize((diameter,diameter),Image.Resampling.LANCZOS)
                image.alpha_composite(flag,(round(cx*W/1678-diameter/2),round(515*H/937-diameter/2)))
            label=str(cfg.get('country_'+side+'_label','')).strip() or str(cfg.get('country_'+side,'')).strip()
            text('country_'+side,label.upper(),cx,699,350,43,42)
            if cfg.get('match_mode')=='Doubles':
                name=cfg['player_'+side]
                text('player_1_'+side,name,cx,231,448,53,52)
                text('partner_'+side,cfg.get('partner_'+side,''),cx,304,448,53,52)
                draw.line((round((cx-155)*W/1678),round(267*H/937),round((cx+155)*W/1678),round(267*H/937)),fill=tuple(cfg['accent_color']),width=max(1,round(2*H/937)))
            else:
                text('player_1_'+side,cfg['player_'+side],cx,267,448,105,78)
        text('day',cfg['day'],838,61,255,32,32)
        text('title',cfg['title'],838,126,375,45,44)
        text('versus',cfg['versus'],831,480,182,160,132,'bold_italic')
        return image

    def render_player_list(cfg):
        W,H=c.BROADCAST_SIZES.get(cfg.get('canvas_size'),(1920,1080))
        source=c.load_photo(cfg.get('background_path') or str(root/'player_list_background.png'))
        image=Image.new('RGBA',(W,H),(*cfg['background_color'],255))
        if source is not None:
            ratio=max(W/source.width,H/source.height)
            source=source.resize((max(W,round(source.width*ratio)),max(H,round(source.height*ratio))),Image.Resampling.LANCZOS)
            image.alpha_composite(source,((W-source.width)//2,(H-source.height)//2))
        scale=c.clamp_number(cfg.get('band_size_pct'),10,200,100)/100
        pw=max(40,round(W*cfg['panel_width_pct']/100*scale))
        ph=max(80,round(H*cfg['panel_height_pct']/100*scale))
        panel=Image.new('RGBA',(pw,ph))
        draw=ImageDraw.Draw(panel)
        top=tuple(cfg['panel_color']);bottom=tuple(cfg['panel_color_2'])
        if cfg.get('panel_style')=='gradient':
            for y in range(ph):
                t=y/max(1,ph-1)
                draw.line((0,y,pw,y),fill=tuple(round(a+(b-a)*t) for a,b in zip(top,bottom))+(255,))
        else:
            draw.rectangle((0,0,pw-1,ph-1),fill=top+(255,))
        border=max(1,round(W/960))
        draw.rectangle((0,0,pw-1,ph-1),outline=tuple(cfg['border_color']),width=border)
        pad=round(pw*.065)
        if cfg['template']=='t21':
            draw.rectangle((pad,round(ph*.255),pw-pad,round(ph*.259)),fill=tuple(cfg['accent_color']))

        def label(role,value,y,max_height,size,color,uppercase=False):
            value=c.apply_text_case(cfg,role,str(value))
            if uppercase and not c._text_role_override(cfg,role,'case'):
                value=value.upper()
            color,size=c.styled_text(cfg,role,tuple(color),round(size))
            factory=c.text_font_factory(cfg,role,'bold',value)
            lines=c.country_text_lines(draw,value,factory(size),pw-2*pad) if role=='country' else [' '.join(value.split())]
            while size>1:
                font=factory(size)
                if max(c.text_bbox(draw,line,font)[0] for line in lines)<=pw-2*pad and len(lines)*size*1.15<=max_height:
                    break
                size-=1
            for i,line in enumerate(lines):
                c.draw_text(draw,(pad,round(y+(i-(len(lines)-1)/2)*size*1.15)),line,factory(size),color,anchor='lm')

        if cfg['template']=='t22':
            count=int(c.clamp_number(cfg.get('row_count'),1,12,5))
            def cell(role,value,x,y,width,height,size,color):
                value=c.apply_text_case(cfg,role,' '.join(str(value).split()))
                color,size=c.styled_text(cfg,role,tuple(color),round(size))
                factory=c.text_font_factory(cfg,role,'bold',value)
                font=c.fit_font(draw,value,max(1,round(width)),size,minimum=1,factory=factory)
                while c.text_bbox(draw,value,font)[1]>height and font.size>1:
                    font=factory(font.size-1)
                c.draw_text(draw,(round(x),round(y)),value,font,color,anchor='lm')
            margin=pw*.035
            half=pw*.5
            row_h=ph*.64/count
            for side,offset in (('a',0),('b',half)):
                country=cfg.get('country_'+side,'')
                code=c.qualifier_country_code(country)
                if code:
                    with zipfile.ZipFile(root/'country_flags.zip') as archive:
                        flag=Image.open(io.BytesIO(archive.read(code+'.png'))).convert('RGBA')
                    flag.thumbnail((max(1,round(pw*.07)),max(1,round(ph*.075))),Image.Resampling.LANCZOS)
                    panel.alpha_composite(flag,(round(offset+margin),round(ph*.06)))
                cell('country_'+side,country.upper(),offset+pw*.125,ph*.098,pw*.34,ph*.095,ph*.070,cfg['country_color'])
                draw.line((round(offset+margin),round(ph*.18),round(offset+half-margin),round(ph*.18)),fill=tuple(cfg['accent_color']),width=max(2,round(H/270)))
                cell('headers',cfg['player_header_'+side],offset+margin,ph*.24,pw*.265,ph*.065,ph*.038,cfg['accent_color'])
                cell('headers',cfg['ranking_header_'+side],offset+pw*.335,ph*.24,pw*.13,ph*.065,ph*.038,cfg['accent_color'])
                for i in range(count):
                    y=ph*.31+row_h*(i+.5)
                    cell('name_'+side+'_'+str(i+1),cfg.get('name_'+side+'_'+str(i+1),''),offset+margin,y,pw*.275,row_h*.72,ph*.049,cfg['panel_text_color'])
                    cell('rank_'+side+'_'+str(i+1),cfg.get('rank_'+side+'_'+str(i+1),''),offset+pw*.335,y,pw*.13,row_h*.72,ph*.046,cfg['panel_text_color'])
                    if i<count-1:
                        yy=round(ph*.31+row_h*(i+1))
                        draw.line((round(offset+margin),yy,round(offset+half-margin),yy),fill=tuple(cfg['divider_color']),width=max(1,round(H/1080)))
                xx=round(offset+pw*.32)
                draw.line((xx,round(ph*.21),xx,round(ph*.95)),fill=tuple(cfg['divider_color']),width=max(1,round(H/1080)))
            draw.line((round(half),round(ph*.045),round(half),round(ph*.95)),fill=tuple(cfg['border_color']),width=max(1,round(W/960)))
            cx=W*c.clamp_number(cfg.get('band_x_pct'),-50,150,50)/100
            cy=H*c.clamp_number(cfg.get('band_y_pct'),-50,150,50)/100
            image.alpha_composite(panel,(round(cx-pw/2),round(cy-ph/2)))
            return image.convert('RGB')

        country=cfg.get('country','')
        code=c.qualifier_country_code(country)
        if code:
            with zipfile.ZipFile(root/'country_flags.zip') as archive:
                flag=Image.open(io.BytesIO(archive.read(code+'.png'))).convert('RGBA')
            flag.thumbnail((round(pw*.17),round(ph*.085)),Image.Resampling.LANCZOS)
            panel.alpha_composite(flag,(pad,round(ph*.045)))
        label('country',country,ph*.19,ph*.115,ph*.076,cfg['country_color'],True)
        count=int(c.clamp_number(cfg.get('row_count'),1,12,5))
        row_h=ph*.70/count
        for index in range(count):
            y=ph*.255+row_h*(index+.5)
            label('player_'+str(index+1),cfg.get('player_'+str(index+1),''),y,row_h*.72,ph*.058,cfg['panel_text_color'])
            if index<count-1:
                line_y=round(ph*.255+row_h*(index+1))
                draw.line((pad,line_y,pw-pad,line_y),fill=tuple(cfg['divider_color']),width=max(1,round(H/1080)))
        cx=W*c.clamp_number(cfg.get('band_x_pct'),-50,150,50)/100
        cy=H*c.clamp_number(cfg.get('band_y_pct'),-50,150,50)/100
        image.alpha_composite(panel,(round(cx-pw/2),round(cy-ph/2)))
        return image.convert('RGB')

    def render_qualifier_band(cfg):
        W,H = c.BROADCAST_SIZES.get(cfg.get('canvas_size'),(1920,1080))
        image = Image.new('RGBA',(W,H))
        with Image.open(root/'qualifier_band.png') as source:
            art = source.convert('RGBA').resize((1672,941),Image.Resampling.LANCZOS).crop((85,685,1587,903))
        art = c.adjust_source_image(art,cfg)
        draw = ImageDraw.Draw(art)

        def text(role,value,x,y,width,height,size,color):
            value = c.apply_text_case(cfg,role,str(value))
            color,size = c.styled_text(cfg,role,tuple(cfg[color]),size)
            factory = c.text_font_factory(cfg,role,'bold',value)
            lines = c.country_text_lines(draw,value,factory(size),width) if role.startswith('country_') else [value]
            while size > 1:
                font = factory(size)
                if max(c.text_bbox(draw,line,font)[0] for line in lines)<=width and len(lines)*size*1.15<=height:
                    break
                size -= 1
            for index,line in enumerate(lines):
                c.draw_text_centered(draw,line,factory(size),x,round(y+(index-(len(lines)-1)/2)*size*1.15),color)

        def flag(country,x):
            code = c.qualifier_country_code(country)
            if not code:
                return
            try:
                with zipfile.ZipFile(root/'country_flags.zip') as archive:
                    source = Image.open(io.BytesIO(archive.read(code+'.png'))).convert('RGBA')
            except (KeyError,OSError,zipfile.BadZipFile):
                return
            size=126
            ratio=max(size/source.width,size/source.height)
            source=source.resize((round(source.width*ratio),round(source.height*ratio)),Image.Resampling.LANCZOS)
            left=(source.width-size)//2;top=(source.height-size)//2
            source=source.crop((left,top,left+size,top+size))
            mask=Image.new('L',(size,size));ImageDraw.Draw(mask).ellipse((0,0,size-1,size-1),fill=255)
            source.putalpha(mask)
            art.alpha_composite(source,(x-size//2,135-size//2))

        flag(cfg['country_a'],126);flag(cfg['country_b'],1374)
        text('title',cfg['title'],590,29,235,42,34,'title_color')
        text('date_text',cfg['date_text'],877,29,280,36,22,'date_color')
        text('country_a',cfg['country_a_label'] or cfg['country_a'].upper(),387,140,270,120,55,'country_color')
        text('country_b',cfg['country_b_label'] or cfg['country_b'].upper(),1110,140,270,120,55,'country_color')
        text('score_a',cfg['score_a'],656,140,155,150,140,'score_a_color')
        text('score_b',cfg['score_b'],838,140,155,150,140,'score_b_color')
        draw.line((725,10,725,45),fill=tuple(cfg['divider_color']),width=2)
        draw.line((751,102,751,180),fill=tuple(cfg['divider_color']),width=3)
        scale=W*.90/art.width*c.clamp_number(cfg.get('band_size_pct'),10,200,100)/100
        art=art.resize((max(1,round(art.width*scale)),max(1,round(art.height*scale))),Image.Resampling.LANCZOS)
        opacity=c.clamp_number(cfg.get('overlay_opacity_pct'),0,100,100)/100
        if opacity<1:
            art.putalpha(art.getchannel('A').point(lambda v:round(v*opacity)))
        x=W*c.clamp_number(cfg.get('band_x_pct'),-50,150,50)/100
        y=H*c.clamp_number(cfg.get('band_y_pct'),-50,150,84)/100
        image.alpha_composite(art,(round(x-art.width/2),round(y-art.height/2)))
        return image

    def render_custom_band(cfg):
        W,H = c.BROADCAST_SIZES.get(cfg.get('canvas_size'),(1920,1080))
        image = Image.new('RGBA',(W,H),(0,0,0,0))
        source = c.load_photo(cfg.get('band_path',''))
        if source is None or not source.width or not source.height:
            return image
        source = source.convert('RGBA')
        alpha_box = source.getchannel('A').getbbox()
        if alpha_box:
            source = source.crop(alpha_box)
        scale = c.clamp_number(cfg.get('band_size_pct'),10,200,100)/100
        fit = min(W*.90/source.width,H*.80/source.height)*scale
        size = (max(1,round(source.width*fit)),max(1,round(source.height*fit)))
        source = source.resize(size,Image.Resampling.LANCZOS)
        opacity = c.clamp_number(cfg.get('overlay_opacity_pct'),0,100,100)/100
        if opacity < 1:
            source.putalpha(source.getchannel('A').point(lambda value: round(value*opacity)))
        center_x = W*c.clamp_number(cfg.get('band_x_pct'),-50,150,50)/100
        center_y = H*c.clamp_number(cfg.get('band_y_pct'),-50,150,75)/100
        image.alpha_composite(source,(round(center_x-source.width/2),round(center_y-source.height/2)))
        return image

    def render_text_band(cfg,key):
        W,H = c.BROADCAST_SIZES.get(cfg.get('canvas_size'),(1920,1080))
        image = Image.new('RGBA',(W,H),(0,0,0,0))
        art_size = (1500,160) if key == 't16' else (1260,140)
        art = Image.new('RGBA',art_size,(0,0,0,0))
        draw = ImageDraw.Draw(art,'RGBA')
        green = tuple(c.normalize_rgb(cfg.get('green_color'),(0,92,57)))
        accent = tuple(c.normalize_rgb(cfg.get('accent_color'),(20,205,70)))

        def fitted_text(value,role,cx,cy,max_width,size,color):
            value = c.apply_text_case(cfg,role,str(value).replace('\n',' '))
            styled_color,styled_size = c.styled_text(cfg,role,color,size)
            font = c.fit_font(draw,value,max_width,styled_size,minimum=14,
                              factory=c.text_font_factory(cfg,role,'bold',value))
            c.draw_text_centered(draw,value,font,cx,cy,styled_color)

        if key == 't16':
            white = tuple(c.normalize_rgb(cfg.get('white_color'),(246,247,243)))
            left_text = tuple(c.normalize_rgb(cfg.get('text_a_color'),(255,255,255)))
            right_text = tuple(c.normalize_rgb(cfg.get('text_b_color'),green))
            draw.polygon([(35,14),(815,14),(755,146),(0,146)],fill=(*green,255))
            draw.polygon([(790,14),(1465,14),(1500,146),(730,146)],fill=(*white,255))
            draw.polygon([(12,14),(42,14),(8,146),(0,146)],fill=(*accent,255))
            draw.polygon([(1467,14),(1490,14),(1500,146),(1478,146)],fill=(*accent,255))
            fitted_text(cfg.get('text_a',''),'text_a',390,80,650,62,left_text)
            fitted_text(cfg.get('text_b',''),'text_b',1110,80,610,57,right_text)
        else:
            text_color = tuple(c.normalize_rgb(cfg.get('text_color'),(255,255,255)))
            draw.polygon([(28,10),(1235,10),(1260,130),(0,130)],fill=(*green,255))
            draw.polygon([(7,10),(34,10),(10,130),(0,130)],fill=(*accent,255))
            draw.polygon([(1237,10),(1250,10),(1260,130),(1247,130)],fill=(*accent,255))
            fitted_text(cfg.get('text',''),'text',630,70,1080,64,text_color)

        base_scale = min(W/1920,H/1080)
        scale = base_scale*c.clamp_number(cfg.get('band_size_pct'),10,200,100)/100
        art = art.resize((max(1,round(art.width*scale)),max(1,round(art.height*scale))),Image.Resampling.LANCZOS)
        opacity = c.clamp_number(cfg.get('overlay_opacity_pct'),0,100,100)/100
        if opacity < 1:
            art.putalpha(art.getchannel('A').point(lambda value: round(value*opacity)))
        center_x = W*c.clamp_number(cfg.get('band_x_pct'),-50,150,50)/100
        center_y = H*c.clamp_number(cfg.get('band_y_pct'),-50,150,82)/100
        image.alpha_composite(art,(round(center_x-art.width/2),round(center_y-art.height/2)))
        return image

    def render_scoreboard_astern(cfg):
        W,H = c.BROADCAST_SIZES.get(cfg.get('canvas_size'),(1920,1080))
        image = Image.new('RGBA',(W,H),(0,0,0,0))
        count = int(c.clamp_number(cfg.get('set_count'),1,5,3))
        score_left = 600
        score_column_width = 100
        aw,ah = score_left+count*score_column_width,250
        art = Image.new('RGBA',(aw,ah),(0,0,0,0))
        draw = ImageDraw.Draw(art,'RGBA')
        top = tuple(c.normalize_rgb(cfg.get('top_row_color'),(242,242,242)))
        bottom = tuple(c.normalize_rgb(cfg.get('bottom_row_color'),(0,103,61)))
        divider = tuple(c.normalize_rgb(cfg.get('divider_color'),(145,145,145)))
        draw.rectangle((0,8,aw-1,125),fill=(*top,255))
        draw.rectangle((0,125,aw-1,242),fill=(*bottom,255))
        score_width = score_column_width
        for index in range(count):
            x = round(score_left+index*score_width)
            draw.line((x,20,x,230),fill=(*divider,255),width=3)

        def fitted(value,role,x,y,width,size,color,anchor='lm'):
            value = c.apply_text_case(cfg,role,str(value).replace('\n',' '))
            color,size = c.styled_text(cfg,role,color,size)
            font = c.fit_font(draw,value,max(1,round(width)),size,minimum=12,
                              factory=c.text_font_factory(cfg,role,'bold',value))
            if anchor == 'mm':
                c.draw_text_centered(draw,value,font,round(x),round(y),color)
            else:
                c.draw_text(draw,(round(x),round(y)),value,font,color,anchor=anchor)

        def flag(country,y):
            code = c.qualifier_country_code(country)
            if not code:
                return
            try:
                with zipfile.ZipFile(root/'country_flags.zip') as archive:
                    source = Image.open(io.BytesIO(archive.read(code+'.png'))).convert('RGBA')
            except (KeyError,OSError,zipfile.BadZipFile):
                return
            box_w,box_h = 82,60
            ratio = min(box_w/source.width,box_h/source.height)
            source = source.resize((max(1,round(source.width*ratio)),max(1,round(source.height*ratio))),
                                   Image.Resampling.LANCZOS)
            art.alpha_composite(source,(28+(box_w-source.width)//2,round(y-source.height/2)))

        flag(cfg.get('country_a',''),66)
        flag(cfg.get('country_b',''),184)
        fitted(cfg.get('player_a',''),'player_a',125,66,score_left-145,48,
               c.normalize_rgb(cfg.get('top_text_color'),(35,35,35)))
        fitted(cfg.get('player_b',''),'player_b',125,184,score_left-145,48,
               c.normalize_rgb(cfg.get('bottom_text_color'),(255,255,255)))
        scores_a = cfg.get('scores_a') if isinstance(cfg.get('scores_a'),list) else []
        scores_b = cfg.get('scores_b') if isinstance(cfg.get('scores_b'),list) else []
        for index in range(count):
            cx = score_left+(index+.5)*score_width
            fitted(scores_a[index] if index<len(scores_a) else '','score_a',cx,66,
                   score_width-12,58,c.normalize_rgb(cfg.get('top_score_color'),(35,35,35)),'mm')
            fitted(scores_b[index] if index<len(scores_b) else '','score_b',cx,184,
                   score_width-12,58,c.normalize_rgb(cfg.get('bottom_score_color'),(255,255,255)),'mm')
        base_scale = min(W/1920,H/1080)
        scale = base_scale*c.clamp_number(cfg.get('band_size_pct'),10,200,100)/100
        art = art.resize((max(1,round(aw*scale)),max(1,round(ah*scale))),Image.Resampling.LANCZOS)
        opacity = c.clamp_number(cfg.get('overlay_opacity_pct'),0,100,100)/100
        if opacity < 1:
            art.putalpha(art.getchannel('A').point(lambda value:round(value*opacity)))
        center_x = W*c.clamp_number(cfg.get('band_x_pct'),-50,150,50)/100
        center_y = H*c.clamp_number(cfg.get('band_y_pct'),-50,150,82)/100
        image.alpha_composite(art,(round(center_x-art.width/2),round(center_y-art.height/2)))
        return image

    def render(cfg):
        key = cfg['template']
        if key=='t24':
            return render_semi_finals(cfg)
        if key=='t23':
            return render_prediction(cfg)
        if key in ('t21','t22'):
            return render_player_list(cfg)
        if key == 't20':
            return render_qualifier_band(cfg)
        if key == 't15':
            return render_custom_band(cfg)
        if key in ('t16','t17'):
            return render_text_band(cfg,key)
        if key == 't18':
            return render_scoreboard_astern(cfg)
        W,H = c.BROADCAST_SIZES.get(cfg.get('canvas_size'),(1920,1080))
        billie = c._competition_theme.active(cfg)
        transparent = key in ('t11','t19') and bool(cfg.get('transparent_background', True))
        if key == 't19':
            transparent = cfg.get('background_mode','Transparent') == 'Transparent'
        image = Image.new('RGBA' if transparent else 'RGB', (W,H),
                          (0,0,0,0) if transparent else tuple(cfg['background_color']))
        path = cfg.get('background_path') or (root/'match_stadium.png' if key not in ('t11','t19') else '')
        if billie and not cfg.get('background_path') and (key not in ('t11','t19') or cfg.get('background_mode') == 'Image'):
            path = root/'billie_background.png'
        if key == 't19' and cfg.get('background_mode','Transparent') != 'Image':
            path = ''
        background = c.load_photo(str(path)) if path else None
        if background is not None and not transparent:
            fitted = c.cover_crop(background,W,H)
            image.paste(fitted,(0,0),fitted.getchannel('A') if key == 't19' and fitted.mode == 'RGBA' else None)
        if key=='t13':
            return render_news(c,image,cfg)
        if key == 't12' and not billie:
            image = image.filter(ImageFilter.GaussianBlur(W/640))
            image = Image.blend(image,Image.new('RGB',image.size,'black'),.28)
        draw = ImageDraw.Draw(image)
        green=(3,30,77) if billie else (0,57,36); white=(255,255,255); gold=(210,255,36) if billie else (211,181,92)
        accent=tuple(cfg['accent_color'])

        def text(value,cx,cy,width,height,size,color=white,italic=False,role='all'):
            value=c.apply_text_case(cfg,role,str(value).replace('\n',' '))
            color,size_px=c.styled_text(cfg,role,color,round(H*size))
            factory=c.text_font_factory(cfg,role,'bold_italic' if italic else 'bold',value)
            font=c.fit_font(draw,value,max(1,int(W*width)),max(1,size_px),minimum=1,factory=factory)
            while c.text_bbox(draw,value,font)[1]>H*height and font.size>1:
                font=factory(font.size-1)
            c.draw_text_centered(draw,value,font,round(W*cx),round(H*cy),color)

        def panel(x,y,w,h,fill=green,outline=accent,slant=0):
            pts=[(W*(x+slant),H*y),(W*(x+w),H*y),
                 (W*(x+w-slant),H*(y+h)),(W*x,H*(y+h))]
            draw.polygon(pts,fill=fill)
            draw.line(pts+[pts[0]],fill=outline,width=max(1,round(W*.0015)))

        def flag(country,x,y,w,h,radius=.012):
            code=c.qualifier_country_code(country)
            if not code:
                return
            with zipfile.ZipFile(root/'country_flags.zip') as archive:
                source=Image.open(io.BytesIO(archive.read(code+'.png'))).convert('RGB')
            size=(max(1,round(W*w)),max(1,round(H*h)))
            source=source.resize(size,Image.Resampling.LANCZOS)
            mask=Image.new('L',size,0)
            ImageDraw.Draw(mask).rounded_rectangle((0,0,size[0]-1,size[1]-1),round(W*radius),fill=255)
            image.paste(source,(round(W*x),round(H*y)),mask)

        if key not in ('t11','t19') and (not billie or cfg.get('logo_path')):
            logo=c.load_photo(cfg.get('logo_path') or str(root/'match_davis_logo.png'))
            if logo:
                logo_width=max(1,round(W*cfg['logo_size_pct']/100))
                logo=logo.resize((logo_width,max(1,round(logo.height*logo_width/logo.width))),Image.Resampling.LANCZOS)
                image.paste(logo,(int(W*cfg['logo_x_pct']/100-logo.width/2),
                                  int(H*cfg['logo_y_pct']/100-logo.height/2)),logo)
        if key == 't10':
            for side,cx in [('a',.16),('b',.86)]:
                photo=c.load_photo(cfg.get('photo_'+side,''))
                if photo:
                    scale=min(W*.25/photo.width,H*.56/photo.height)*cfg['photo_'+side+'_size_pct']/100
                    photo=photo.resize((max(1,round(photo.width*scale)),max(1,round(photo.height*scale))),Image.Resampling.LANCZOS)
                    image.paste(photo,(round(W*(cx+cfg['photo_'+side+'_offset_x_pct']/100)-photo.width/2),
                                      round(H*(.77+cfg['photo_'+side+'_offset_y_pct']/100)-photo.height)),photo)
            for side,x in [('a',.035),('b',.675)]:
                panel(x,.775,.29,.075,slant=.01)
                text(cfg['player_'+side],x+.145,.812,.255,.062,.05,role='player_'+side)
            panel(.41,.70,.20,.065,slant=.01)
            text(cfg['title'],.51,.733,.17,.055,.058,italic=True,role='title')
            panel(.387,.766,.225,.094,fill=(242,245,247),outline=(181,210,215),slant=.012)
            text(cfg['subtitle'],.5,.813,.197,.08,.068,(0,0,0),True,'subtitle')
            for side,x in [('a',.305),('b',.645)]:
                flag(cfg['country_'+side],x,.525,.07,.085)
            for side,x in [('a',.38),('b',.565)]:
                panel(x,.525,.073,.085)
                text(c.qualifier_country_label(cfg['country_'+side]),x+.0365,.567,.066,.065,.046,italic=True,role='country_'+side)
            text('VS',.503,.567,.073,.07,.055,role='versus')
        elif key == 't19':
            scale=cfg['band_size_pct']/100
            ox=cfg['band_x_pct']/100; oy=cfg['band_y_pct']/100
            def bx(x): return ox+(x-.5)*scale
            def by(y): return oy+(y-.8)*scale
            def color(field): return tuple(cfg[field])
            for side,cx,label in [('a',.23,'left'),('b',.77,'right')]:
                photo=c.load_photo(cfg.get('photo_'+side,''))
                if photo:
                    fit=min(W*.28/photo.width,H*.38/photo.height)*scale*cfg['photo_'+side+'_size_pct']/100
                    photo=photo.resize((max(1,round(photo.width*fit)),max(1,round(photo.height*fit))),Image.Resampling.LANCZOS).convert('RGBA')
                    position=(round(W*(bx(cx)+cfg['photo_'+side+'_offset_x_pct']/100)-photo.width/2),
                              round(H*(by(.79)+cfg['photo_'+side+'_offset_y_pct']/100)-photo.height))
                    if transparent:
                        image.alpha_composite(photo,position)
                    else:
                        image.paste(photo,position,photo)
                panel(bx(cx-.18),by(.79),.36*scale,.085*scale,
                      fill=color(label+'_panel_color'),slant=.012*scale)
                text(cfg['player_'+side],bx(cx),by(.8325),.32*scale,.065*scale,.05*scale,
                     color(label+'_text_color'),role='player_'+side)
                country=cfg['country_'+side]
                flag_x=cx-.104 if side == 'a' else cx+.039
                box_x=cx-.026 if side == 'a' else cx-.104
                flag(country,bx(flag_x),by(.885),.065*scale,.065*scale,radius=.006*scale)
                panel(bx(box_x),by(.885),.13*scale,.065*scale,
                      fill=color(label+'_country_panel_color'))
                text(c.qualifier_country_label(country),bx(box_x+.065),by(.9175),
                     .115*scale,.052*scale,.045*scale,
                     color(label+'_country_text_color'),italic=True,role='country_'+side)
            panel(bx(.365),by(.655),.27*scale,.082*scale,
                  fill=color('title_box_color'),slant=.012*scale)
            text(cfg['title'],ox,by(.696),.24*scale,.06*scale,.046*scale,
                 color('title_text_color'),role='title')
            panel(bx(.448),by(.79),.104*scale,.085*scale,
                  fill=color('versus_panel_color'),outline=color('versus_outline_color'))
            text(cfg['versus'],ox,by(.8325),.088*scale,.065*scale,.052*scale,
                 color('versus_text_color'),role='versus')
        elif key == 't11':
            scale=cfg['band_size_pct']/100
            ox=cfg['band_x_pct']/100; oy=cfg['band_y_pct']/100
            def bx(x): return ox+(x-.5)*scale
            title_box=tuple(c.normalize_rgb(cfg.get('title_box_color'),green))
            title_alpha=round(255*c.clamp_number(cfg.get('title_box_opacity_pct'),0,100,100)/100)
            panel(bx(.165),oy-.155*scale,.67*scale,.09*scale,
                  fill=(*title_box,title_alpha),outline=accent,slant=.012*scale)
            text(cfg['title'],ox,oy-.11*scale,.63*scale,.066*scale,.072*scale,role='title')
            for side,x,code_x in [('a',.195,.298),('b',.682,.54)]:
                flag(cfg['country_'+side],bx(x),oy-.045*scale,.09*scale,.10*scale)
                panel(bx(code_x),oy-.045*scale,.13*scale,.10*scale,fill=(245,245,238),outline=gold)
                text(c.qualifier_country_label(cfg['country_'+side]),bx(code_x+.065),oy+.005*scale,.115*scale,.082*scale,.077*scale,green,True,'country_'+side)
            panel(bx(.44),oy-.045*scale,.087*scale,.10*scale,outline=gold)
            text('VS',bx(.484),oy+.005*scale,.08*scale,.085*scale,.08*scale,gold,role='versus')
        else:
            text(cfg['title'],.5,.2,.86,.1,.085,role='title')
            text(cfg['subtitle'],.5,.28,.78,.068,.056,(255,221,165),role='subtitle')
            for side,x in [('a',.12),('b',.64)]:
                flag(cfg['country_'+side],x,.47,.255,.30,.025)
                text(cfg['country_'+side],x+.1275,.82,.28,.066,.062,role='country_'+side)
            text('VS',.5,.57,.19,.14,.115,role='versus')
            text(cfg['date_text'],.5,.875,.56,.062,.06,role='date_text')
            text(cfg['venue'],.5,.95,.78,.055,.042,role='venue')
        if transparent:
            opacity = c.clamp_number(cfg.get('overlay_opacity_pct'), 0, 100, 100) / 100
            image.putalpha(image.getchannel('A').point(lambda value: round(value * opacity)))
        return image

    for key,default in defaults.items():
        default['template']=key
        namespace['DEFAULT_CONFIGS'][key]=copy.deepcopy(default)
        namespace['RENDERERS'][key]=render
        namespace['TEXT_STYLE_TARGETS'][key]=[('all','All text')]
    namespace['TEXT_STYLE_TARGETS']['t13']=[('all','All text'),('rail_text','Left column'),('headline','Headline'),('subject','Subject')]
    namespace['TEXT_STYLE_TARGETS']['t10']=[('all','All text'),('title','Title'),('subtitle','Subtitle'),
        ('player_a','Left player'),('player_b','Right player'),('country_a','Left country'),
        ('country_b','Right country'),('versus','VS')]
    namespace['TEXT_STYLE_TARGETS']['t11']=[('all','All text'),('title','Coming Next title'),
        ('country_a','Left country'),('country_b','Right country'),('versus','VS')]
    namespace['TEXT_STYLE_TARGETS']['t12']=[('all','All text'),('title','Title'),('subtitle','Subtitle'),
        ('country_a','Left country'),('country_b','Right country'),('versus','VS'),
        ('date_text','Date'),('venue','Venue')]
    namespace['TEXT_STYLE_TARGETS']['t16']=[('all','All text'),('text_a','Left text'),('text_b','Right text')]
    namespace['TEXT_STYLE_TARGETS']['t17']=[('all','All text'),('text','Band text')]
    namespace['TEXT_STYLE_TARGETS']['t18']=[('all','All text'),('player_a','Top player'),
        ('player_b','Bottom player'),('score_a','Top scores'),('score_b','Bottom scores')]
    namespace['TEXT_STYLE_TARGETS']['t19']=[('all','All text'),('title','Coming Next title'),
        ('player_a','Left player name'),('player_b','Right player name'),('versus','VS'),
        ('country_a','Left country'),('country_b','Right country')]
    namespace['TEXT_STYLE_TARGETS']['t20']=[('all','All text'),('title','Title'),('date_text','Date'),('country_a','Left country'),('country_b','Right country'),('score_a','Left score'),('score_b','Right score')]
    namespace['TEXT_STYLE_TARGETS']['t21']=[('all','All text'),('country','Country')]+[('player_'+str(i),'Player '+str(i)) for i in range(1,13)]
    namespace['TEXT_STYLE_TARGETS']['t22']=[('all','All text'),('country_a','Left country'),('country_b','Right country'),('headers','Column headings')]+[(field+'_'+side+'_'+str(i),('Left' if side=='a' else 'Right')+' '+field+' '+str(i)) for side in ('a','b') for i in range(1,13) for field in ('name','rank')]
    namespace['WEB_TEMPLATE_KEYS']+=tuple(defaults)
    namespace['TEXT_STYLE_TARGETS']['t24']=[('all','All text'),('day','Day'),('title','Heading'),('country_a','Left country label'),('country_b','Right country label'),('versus','VS'),('player_1_a','Left player 1'),('partner_a','Left player 2'),('player_1_b','Right player 1'),('partner_b','Right player 2')]
    namespace['WEB_TEMPLATE_NAMES']+=['Match Day','Coming Next','Quarter Finals','News Headline','Custom Band','Aston Band','Slug Band','Scoreboard Astern','Coming Next V2','Qualifier Band','Player List','COUNTRY VS','Predection','Semi Finals']

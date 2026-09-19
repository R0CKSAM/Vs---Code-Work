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
        layout.set_width(max(1,width-round(80*H/1080))*Pango.SCALE)
        layout.set_wrap(Pango.WrapMode.WORD_CHAR)
        requested=layout.get_pixel_size()[1]+round(80*H/1080)
    else:
        font=c.text_font(cfg,'headline',size,'bold')
        draw=ImageDraw.Draw(Image.new('RGB',(1,1)))
        available=max(1,width-round(80*H/1080))
        lines=sum(max(1,int(c.text_bbox(draw,line,font)[0]/available)+1) for line in text.split('\n'))
        requested=round(lines*size*1.3+80*H/1080)
    height=max(round(H*.12),min(round(H*.22),requested))
    if not cfg.get('auto_text_height',True):
        height=round(H*cfg.get('headline_height_pct',16)/100)
    top=round(H*.27);gap=round(H*.024)
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
        value=' '.join(value.split())
    background=c.normalize_rgb(cfg.get(role+'_box_color'),(0,60,46))
    layer=Image.new('RGBA',size,(*background,round(255*cfg['box_opacity_pct']/100)))
    if not value.strip():
        return layer
    color,requested=c.styled_text(cfg,role,c.readable_text_colors(background)[0],
                                 round(cfg[role+'_font_size']*cfg['_news_scale']))
    padding=max(1,round(24*cfg['_news_scale']))
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
            if max(ink.height,logical.height)<=ah and ink.width<=aw and (role!='headline' or layout(mid).get_line_count()<=2):
                lo=mid
            else:
                hi=mid-1
        text=layout(lo)
        ink,logical=text.get_pixel_extents()
        context.set_source_rgb(*(channel/255 for channel in color))
        context.move_to(padding,min(padding,padding-ink.y))
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
        if bb[2]-bb[0]<=aw and bb[3]-bb[1]<=ah and (role!='headline' or len(layout(mid)[1].split('\n'))<=2): lo=mid
        else: hi=mid-1
    font,text,spacing,bb=layout(lo)
    align=cfg[role+'_align']
    x=padding if align=='left' else w-padding-(bb[2]-bb[0]) if align=='right' else (w-bb[2]+bb[0])/2
    draw.multiline_text((x-bb[0],padding-bb[1]),text,font=font,fill=(*color,255),spacing=spacing,align=align)
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
        image_box=(x+(w-fw)//2,y+(h-fh)//2,fw,fh)
    left=Image.new('RGBA',(image_box[2]-2*inset,image_box[3]-2*inset),(0,0,0,0))
    if source:
        scale=min(left.width/source.width,left.height/source.height)*cfg['image_size_pct']/100
        source=source.resize((max(1,round(source.width*scale)),max(1,round(source.height*scale))),Image.Resampling.LANCZOS)
        left.alpha_composite(source,(round(left.width*.5-source.width*.5+W*cfg['image_offset_x_pct']/100),
                                     round(left.height*.5-source.height*.5+H*cfg['image_offset_y_pct']/100)))
    panel(image_box,(0,65,49),left)
    for role,box in zip(('headline','subject'),news_layout(c,cfg,W,H)):
        x,y,w,h=box
        layer=news_text_layer(c,dict(cfg,_news_scale=H/1080,box_opacity_pct=0),role,(w-2*inset,h-2*inset))
        panel(box,c.normalize_rgb(cfg.get(role+'_box_color'),(0,65,49)),layer)
    rail=(round(W*.025),round(H*.09),round(W*.085),round(H*.83))
    rail_cfg=dict(cfg,headline='NEWS HEADLINE',headline_align='center',headline_font_size=70,
                  box_opacity_pct=0,_news_scale=H/1080)
    text=news_text_layer(c,rail_cfg,'headline',(rail[3]-2*inset,rail[2]-2*inset)).rotate(90,expand=True)
    panel(rail,(0,54,42),text)
    if cfg.get('show_logo',True):
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
                   headline_align='center',subject_align='left',headline_box_color=[0,68,52],
                   subject_box_color=[0,68,52],box_opacity_pct=94,
                   image_offset_x_pct=0,image_offset_y_pct=0,image_size_pct=100),
        't15':dict(canvas_size='HD  (1920x1080)',band_path='',band_x_pct=50,band_y_pct=75,
                   band_size_pct=100,overlay_opacity_pct=100,background_color=[0,0,0],
                   accent_color=[0,229,117],text_styles={},rows=[]),
    }

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

    def render(cfg):
        key = cfg['template']
        if key == 't15':
            return render_custom_band(cfg)
        W,H = c.BROADCAST_SIZES.get(cfg.get('canvas_size'),(1920,1080))
        transparent = key == 't11' and bool(cfg.get('transparent_background', True))
        image = Image.new('RGBA' if transparent else 'RGB', (W,H),
                          (0,0,0,0) if transparent else tuple(cfg['background_color']))
        path = cfg.get('background_path') or (root/'match_stadium.png' if key!='t11' else '')
        background = c.load_photo(str(path)) if path else None
        if background is not None and not transparent:
            image.paste(c.cover_crop(background,W,H))
        if key=='t13':
            return render_news(c,image,cfg)
        if key == 't12':
            image = image.filter(ImageFilter.GaussianBlur(W/640))
            image = Image.blend(image,Image.new('RGB',image.size,'black'),.28)
        draw = ImageDraw.Draw(image)
        green=(0,57,36); white=(255,255,255); gold=(211,181,92)
        accent=tuple(cfg['accent_color'])

        def text(value,cx,cy,width,height,size,color=white,italic=False):
            value=c.apply_text_case(cfg,'all',str(value).replace('\n',' '))
            color,size_px=c.styled_text(cfg,'all',color,round(H*size))
            factory=c.text_font_factory(cfg,'all','bold_italic' if italic else 'bold')
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

        if key != 't11':
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
                text(cfg['player_'+side],x+.145,.812,.255,.062,.05)
            panel(.41,.70,.20,.065,slant=.01)
            text(cfg['title'],.51,.733,.17,.055,.058,italic=True)
            panel(.387,.766,.225,.094,fill=(242,245,247),outline=(181,210,215),slant=.012)
            text(cfg['subtitle'],.5,.813,.197,.08,.068,(0,0,0),True)
            for side,x in [('a',.305),('b',.645)]:
                flag(cfg['country_'+side],x,.525,.07,.085)
            for side,x in [('a',.38),('b',.565)]:
                panel(x,.525,.073,.085)
                text(c.qualifier_country_label(cfg['country_'+side]),x+.0365,.567,.066,.065,.046,italic=True)
            text('VS',.503,.567,.073,.07,.055)
        elif key == 't11':
            scale=cfg['band_size_pct']/100
            ox=cfg['band_x_pct']/100; oy=cfg['band_y_pct']/100
            def bx(x): return ox+(x-.5)*scale
            title_box=tuple(c.normalize_rgb(cfg.get('title_box_color'),green))
            title_alpha=round(255*c.clamp_number(cfg.get('title_box_opacity_pct'),0,100,100)/100)
            panel(bx(.165),oy-.155*scale,.67*scale,.09*scale,
                  fill=(*title_box,title_alpha),outline=accent,slant=.012*scale)
            text(cfg['title'],ox,oy-.11*scale,.63*scale,.066*scale,.072*scale)
            for side,x,code_x in [('a',.195,.298),('b',.682,.54)]:
                flag(cfg['country_'+side],bx(x),oy-.045*scale,.09*scale,.10*scale)
                panel(bx(code_x),oy-.045*scale,.13*scale,.10*scale,fill=(245,245,238),outline=gold)
                text(c.qualifier_country_label(cfg['country_'+side]),bx(code_x+.065),oy+.005*scale,.115*scale,.082*scale,.077*scale,green,True)
            panel(bx(.44),oy-.045*scale,.087*scale,.10*scale,outline=gold)
            text('VS',bx(.484),oy+.005*scale,.08*scale,.085*scale,.08*scale,gold)
        else:
            text(cfg['title'],.5,.2,.86,.1,.085)
            text(cfg['subtitle'],.5,.28,.78,.068,.056,(255,221,165))
            for side,x in [('a',.12),('b',.64)]:
                flag(cfg['country_'+side],x,.47,.255,.30,.025)
                text(cfg['country_'+side],x+.1275,.82,.28,.066,.062)
            text('VS',.5,.57,.19,.14,.115)
            text(cfg['date_text'],.5,.875,.56,.062,.06)
            text(cfg['venue'],.5,.95,.78,.055,.042)
        if transparent:
            opacity = c.clamp_number(cfg.get('overlay_opacity_pct'), 0, 100, 100) / 100
            image.putalpha(image.getchannel('A').point(lambda value: round(value * opacity)))
        return image

    for key,default in defaults.items():
        default['template']=key
        namespace['DEFAULT_CONFIGS'][key]=copy.deepcopy(default)
        namespace['RENDERERS'][key]=render
        namespace['TEXT_STYLE_TARGETS'][key]=[('all','All text')]
    namespace['TEXT_STYLE_TARGETS']['t13']=[('all','All text'),('headline','Headline'),('subject','Subject')]
    namespace['WEB_TEMPLATE_KEYS']+=tuple(defaults)
    namespace['WEB_TEMPLATE_NAMES']+=['Match Day','Coming Next','Quarter Finals','News Headline','Custom Band']

"""Editable broadcast layouts adapted from the supplied three Qt designs."""
import copy
import io
import zipfile
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageDraw, ImageFilter


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
        't11':dict(common, title='COMING NEXT', band_x_pct=50, band_y_pct=88, band_size_pct=100),
        't12':dict(common, title='QUARTER FINALS 2026', subtitle='Match 1 - Round 2',
                   date_text='', venue='', country_a='Japan', country_b='Spain',
                   logo_y_pct=6.5,logo_size_pct=10),
    }

    def render(cfg):
        key = cfg['template']
        W,H = c.BROADCAST_SIZES.get(cfg.get('canvas_size'),(1920,1080))
        image = Image.new('RGB',(W,H),tuple(cfg['background_color']))
        path = cfg.get('background_path') or (root/'match_stadium.png' if key!='t11' else '')
        background = c.load_photo(str(path)) if path else None
        if background is not None:
            image.paste(c.cover_crop(background,W,H))
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
            text(cfg['title'],ox,oy-.078*scale,.63*scale,.075*scale,.082*scale)
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
        return image

    for key,default in defaults.items():
        default['template']=key
        namespace['DEFAULT_CONFIGS'][key]=copy.deepcopy(default)
        namespace['RENDERERS'][key]=render
        namespace['TEXT_STYLE_TARGETS'][key]=[('all','All text')]
    namespace['WEB_TEMPLATE_KEYS']+=tuple(defaults)
    namespace['WEB_TEMPLATE_NAMES']+=['Match Day','Coming Next','Quarter Finals']

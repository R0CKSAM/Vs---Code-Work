"""Competition-scoped palette and artwork, without modifying uploaded media."""
import copy
from pathlib import Path
from PIL import Image, ImageDraw

BILLIE = 'billie-jean-king-cup'
NAVY = [3, 30, 77]
BLUE = [0, 70, 225]
LIME = [210, 255, 36]
WHITE = [246, 247, 252]


def active(cfg):
    return cfg.get('competition_theme') == BILLIE


def apply(template, cfg, competition):
    cfg = copy.deepcopy(cfg)
    if competition != BILLIE:
        cfg['competition_theme'] = 'davis-cup'
        return cfg
    if template in ('t20','t21','t22','t23','t24'):
        cfg.update(competition_theme=BILLIE,theme_revision=1)
        return cfg
    if cfg.get('competition_theme') == BILLIE and cfg.get('theme_revision') == 1:
        return cfg
    if template == 't14':
        cfg['player_outline_px'] = 0
    navy = {'panel_color','band_green','band_green_dark','stats_green','country_text_color',
            'title_box_color','headline_box_color','subject_box_color','green_color',
            'text_b_color','bottom_row_color','top_text_color','top_score_color',
            'left_panel_color','right_panel_color','left_country_text_color',
            'right_country_text_color','versus_panel_color','label_color'}
    lime = {'accent_color','accent_green','bar_color','versus_text_color','versus_outline_color'}
    white = {'panel_white','white_color','top_row_color','left_country_panel_color',
             'right_country_panel_color','name_text_color','text_a_color','text_color',
             'left_text_color','right_text_color','title_text_color','bottom_text_color','bottom_score_color'}
    for field in cfg:
        if field in navy: cfg[field] = NAVY[:]
        elif field in lime: cfg[field] = LIME[:]
        elif field in white: cfg[field] = WHITE[:]
        elif field in ('accent_dark','panel_color_2'): cfg[field] = BLUE[:]
        elif field in ('separator_color','divider_color'): cfg[field] = [104,150,232]
    cfg['background_color'] = NAVY[:]
    if 'background_path' in cfg: cfg['background_path'] = ''
    if template == 't1': cfg['photo_path'] = ''
    if template == 't6': cfg['stats_theme'] = BILLIE
    for field in ('header_text','title','subtitle','banner_text'):
        if isinstance(cfg.get(field),str):
            cfg[field]=cfg[field].replace('DAVIS CUP','BILLIE JEAN KING CUP').replace('Davis Cup','Billie Jean King Cup')
    for row in cfg.get('rows',[]):
        if isinstance(row,dict) and isinstance(row.get('label'),str):
            row['label']=row['label'].replace('Davis Cup','BJK Cup')
    # Keep operator typography/position choices, while updating inherited green ink.
    for style in cfg.get('text_styles',{}).values():
        color=style.get('color')
        if isinstance(color,list) and len(color)==3 and color[1]>color[0]*1.2 and color[1]>color[2]*1.2:
            style['color'] = NAVY[:] if max(color)<180 else LIME[:]
    if template=='t12':
        for role in ('title','subtitle'):
            style=cfg.setdefault('text_styles',{}).setdefault(role,{})
            style.update(box_enabled=True,box_color=NAVY[:],box_opacity_pct=95,box_padding_pct=15)
    cfg.update(competition_theme=BILLIE,theme_revision=1)
    return cfg


def background(size):
    with Image.open(Path(__file__).with_name('billie_background.png')) as source:
        return source.convert('RGB').resize(size,Image.Resampling.LANCZOS)


def fixed_background(c,template,size):
    """Rebuild fixed-artwork panels at the existing editable text coordinates."""
    image=background(size)
    W,H=size
    draw=ImageDraw.Draw(image)
    def panel(box,fill,outline=None):
        draw.rectangle(tuple(round(v*(W if i%2==0 else H)) for i,v in enumerate(box)),
                       fill=tuple(fill),outline=tuple(outline) if outline else None,width=max(1,round(W/640)))
    def label(value,cx,cy,width,height,color=WHITE):
        font=c.fit_font(draw,value,round(W*width),round(H*height),minimum=1,factory=c.text_font_factory({},'all','bold',value))
        c.draw_text_centered(draw,value,font,round(W*cx),round(H*cy),tuple(color))
    if template=='t6':
        for title,y in [('AGE',.298),('TOTAL W/L',.449),('DEBUT YEAR',.598)]:
            panel((.505,y-.066,.963,y+.066),NAVY,LIME)
            panel((.77,y-.063,.961,y+.063),WHITE)
            label(title,.627,y,.22,.042)
        panel((.505,.68,.963,.875),WHITE,LIME)
        panel((.506,.681,.962,.752),NAVY)
        label('FAVOURITE HAND',.734,.715,.42,.045)
    elif template=='t7':
        panel((.15,.12,.85,.235),NAVY)
        panel((.15,.232,.85,.237),LIME)
        label('QUALIFIER ROUNDS',.5,.177,.64,.062)
        panel((.15,.285,.85,.415),NAVY)
        panel((.435,.285,.565,.415),LIME)
        panel((.15,.465,.85,.535),NAVY)
        panel((.15,.465,.85,.469),LIME)
        for i in range(5):
            y=.548+i*.070
            panel((.15,y,.85,y+.066),WHITE if i%2==0 else [228,236,250])
            draw.line((round(W*.5),round(H*y),round(W*.5),round(H*(y+.066))),fill=tuple(BLUE),width=max(1,round(W/960)))
        draw.line((round(W*.5),round(H*.475),round(W*.5),round(H*.525)),fill=tuple(LIME),width=max(1,round(W/960)))
    elif template=='t9':
        panel((.30,.15,.708,.295),NAVY,LIME)
        label('HEAD TO HEAD',.504,.222,.38,.058)
        panel((.30,.338,.708,.397),NAVY,LIME)
        for y in (.43,.49,.55,.61,.67,.741):
            panel((.30,y-.028,.708,y+.028),NAVY)
            panel((.423,y-.028,.585,y+.028),WHITE)
        for x0,x1 in ((.015,.305),(.705,.995)):
            panel((x0,.804,x1,.94),NAVY,LIME)
        panel((.34,.808,.668,.928),WHITE,LIME)
    return image

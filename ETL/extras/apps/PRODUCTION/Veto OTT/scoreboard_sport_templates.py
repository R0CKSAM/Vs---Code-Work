"""Small, bounded live overlays for the cricket and weightlifting workspaces."""

from __future__ import annotations

import copy
from types import SimpleNamespace
from PIL import Image, ImageDraw, ImageOps


SPORT_TEMPLATE_KEYS = ('c1', 'w1')
SPORT_TEMPLATE_NAMES = ('Cricket score strip', 'Athlete attempt')


def register(namespace):
    c = SimpleNamespace(**namespace)
    defaults = {
        'c1': dict(
            template='c1', canvas_size='HD  (1920x1080)',
            match_title='MATCH 1', batting_team='IND', bowling_team='AUS',
            runs=0, wickets=0, overs='0.0', batter='BATTER NAME',
            bowler='BOWLER NAME', chase_label='1ST INNINGS',
            batting_logo_path='', bowling_logo_path='',
            transparent_background=True, overlay_opacity_pct=100,
            competition_theme='cricket', text_styles={}, rows=[],
            accent_color=[35, 193, 240], background_color=[4, 20, 46],
            bar_color=None, image_brightness_pct=100,
            image_vibrance_pct=100, image_contrast_pct=100,
        ),
        'w1': dict(
            template='w1', canvas_size='HD  (1920x1080)',
            athlete_name='ATHLETE NAME', country='IND', category='73 KG',
            lift_type='Snatch', attempt_number=1, target_kg=100,
            result='Pending', photo_path='', country_logo_path='',
            photo_fit='cover', photo_focus_x=50, photo_focus_y=50,
            transparent_background=True, overlay_opacity_pct=100,
            competition_theme='weightlifting', text_styles={}, rows=[],
            accent_color=[250, 72, 130], background_color=[5, 22, 50],
            bar_color=None, image_brightness_pct=100,
            image_vibrance_pct=100, image_contrast_pct=100,
        ),
    }

    def text(draw, cfg, value, box, size, minimum, *, color=(255, 255, 255),
             align='left', role='all'):
        value = str(value).strip()
        if not value:
            return
        left, top, right, bottom = box
        width, height = right - left, bottom - top
        factory = c.text_font_factory(cfg, role, 'bold', value)
        font = c.fit_font(draw, value, width, size, minimum=minimum, factory=factory)
        bounds = c.text_bounds(draw, value, font)
        while font.size > minimum and bounds[3] - bounds[1] > height:
            font = factory(font.size - 1)
            bounds = c.text_bounds(draw, value, font)
        ink_width, ink_height = bounds[2] - bounds[0], bounds[3] - bounds[1]
        if ink_width > width or ink_height > height:
            raise ValueError(f'{role.replace("_", " ").capitalize()} is too long for this graphic.')
        x = left if align == 'left' else right - ink_width if align == 'right' else left + (width - ink_width) / 2
        y = top + (height - ink_height) / 2 - bounds[1]
        c.draw_text(draw, (round(x), round(y)), value, font, color)

    def photo(image, path, box, *, fit='contain', focus=(50, 50), source=None):
        source = source if source is not None else c.load_photo(path)
        if source is None:
            return False
        x0, y0, x1, y1 = box
        size = (x1 - x0, y1 - y0)
        if fit == 'cover':
            layer = ImageOps.fit(source.convert('RGBA'), size, Image.Resampling.LANCZOS,
                                 centering=(focus[0] / 100, focus[1] / 100))
        else:
            layer = ImageOps.contain(source.convert('RGBA'), size, Image.Resampling.LANCZOS)
            padded = Image.new('RGBA', size)
            padded.alpha_composite(layer, ((size[0] - layer.width) // 2,
                                          (size[1] - layer.height) // 2))
            layer = padded
        mask = Image.new('L', size)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=14, fill=255)
        layer.putalpha(Image.composite(layer.getchannel('A'), Image.new('L', size), mask))
        image.alpha_composite(layer, (x0, y0))
        return True

    def make_canvas(cfg):
        if cfg.get('canvas_size') not in c.BROADCAST_SIZES:
            raise ValueError('Choose a supported broadcast canvas.')
        return Image.new('RGBA', (1920, 1080), (0, 0, 0, 0))

    def finish(image, cfg):
        opacity = int(c.clamp_number(cfg.get('overlay_opacity_pct'), 0, 100, 100))
        if opacity != 100:
            image.putalpha(image.getchannel('A').point(lambda value: round(value * opacity / 100)))
        if cfg['canvas_size'] != 'HD  (1920x1080)':
            image = image.resize(c.BROADCAST_SIZES[cfg['canvas_size']], Image.Resampling.LANCZOS)
        return image

    def cricket(cfg):
        image = make_canvas(cfg)
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((72, 840, 1848, 1020), radius=24, fill=(4, 20, 46, 242))
        draw.rounded_rectangle((72, 840, 1848, 851), radius=5, fill=(35, 193, 240, 255))
        draw.line((96, 944, 1824, 944), fill=(82, 117, 155, 200), width=2)
        for x in (343, 607, 828, 1112, 1400):
            draw.line((x, 863, x, 932), fill=(76, 113, 150, 180), width=2)
        for path, box in ((cfg['batting_logo_path'], (100, 861, 172, 933)),
                          (cfg['bowling_logo_path'], (854, 861, 926, 933))):
            photo(image, path, box)
        text(draw, cfg, cfg['batting_team'], (182, 866, 331, 924), 50, 25, role='batting_team')
        text(draw, cfg, f"{cfg['runs']}/{cfg['wickets']}", (363, 856, 590, 931), 67, 33, role='score')
        text(draw, cfg, f"{cfg['overs']} OV", (630, 866, 809, 925), 46, 24, role='overs')
        text(draw, cfg, cfg['bowling_team'], (942, 866, 1095, 924), 50, 25, role='bowling_team')
        text(draw, cfg, cfg['chase_label'], (1134, 870, 1380, 921), 34, 20,
             color=(117, 224, 253), role='chase_label')
        text(draw, cfg, cfg['match_title'], (1425, 870, 1820, 921), 36, 20,
             align='right', role='match_title')
        text(draw, cfg, 'BATTER', (100, 955, 210, 991), 23, 18,
             color=(117, 224, 253), role='label')
        text(draw, cfg, cfg['batter'], (218, 952, 820, 998), 36, 20, role='batter')
        text(draw, cfg, 'BOWLER', (858, 955, 994, 991), 23, 18,
             color=(117, 224, 253), role='label')
        text(draw, cfg, cfg['bowler'], (1012, 952, 1817, 998), 36, 20, role='bowler')
        return finish(image, cfg)

    def weightlifting(cfg):
        image = make_canvas(cfg)
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((72, 766, 1848, 1020), radius=24, fill=(5, 22, 50, 245))
        draw.rounded_rectangle((72, 766, 1848, 779), radius=6, fill=(250, 72, 130, 255))
        source = c.load_photo(cfg['photo_path'])
        has_photo = source is not None
        if has_photo:
            draw.rounded_rectangle((100, 789, 314, 998), radius=14, fill=(31, 57, 88, 255))
            photo(image, cfg['photo_path'], (100, 789, 314, 998), fit=cfg['photo_fit'],
                  focus=(cfg['photo_focus_x'], cfg['photo_focus_y']), source=source)
        name_left = 345 if has_photo else 108
        draw.line((1078, 802, 1078, 986), fill=(99, 127, 163), width=2)
        draw.line((1448, 802, 1448, 986), fill=(99, 127, 163), width=2)
        text(draw, cfg, cfg['athlete_name'], (name_left, 804, 1055, 875), 58, 28, role='athlete_name')
        if cfg['country_logo_path']:
            photo(image, cfg['country_logo_path'], (name_left + 2, 895, name_left + 65, 943))
            country_box = (name_left + 80, 893, 635, 946)
        else:
            country_box = (name_left, 893, 635, 946)
        text(draw, cfg, cfg['country'], country_box, 38, 22,
             color=(129, 224, 251), role='country')
        text(draw, cfg, cfg['category'], (668, 893, 1047, 946), 38, 22, role='category')
        text(draw, cfg, cfg['lift_type'].upper(), (1110, 805, 1420, 860), 35, 21,
             color=(129, 224, 251), role='lift_type')
        text(draw, cfg, f"{cfg['target_kg']} KG", (1109, 871, 1421, 961), 75, 36, role='target_kg')
        text(draw, cfg, f"ATTEMPT {cfg['attempt_number']}", (1475, 812, 1820, 871),
             37, 23, role='attempt_number')
        result_color = {'Good lift': (55, 230, 155), 'No lift': (255, 105, 125)}.get(
            cfg['result'], (255, 216, 107))
        draw.rounded_rectangle((1474, 890, 1819, 964), radius=12, fill=(*result_color[:3], 35),
                               outline=(*result_color[:3], 220), width=3)
        text(draw, cfg, cfg['result'].upper(), (1494, 903, 1799, 951), 40, 23,
             color=result_color, align='center', role='result')
        return finish(image, cfg)

    for key, renderer in (('c1', cricket), ('w1', weightlifting)):
        namespace['DEFAULT_CONFIGS'][key] = copy.deepcopy(defaults[key])
        namespace['RENDERERS'][key] = renderer
        namespace['TEXT_STYLE_TARGETS'][key] = [('all', 'All text')]
    namespace['WEB_TEMPLATE_KEYS'] += SPORT_TEMPLATE_KEYS
    namespace['WEB_TEMPLATE_NAMES'] += list(SPORT_TEMPLATE_NAMES)
    namespace['SPORT_TEMPLATE_KEYS'] = SPORT_TEMPLATE_KEYS

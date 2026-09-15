import copy

import pytest
from PIL import Image, ImageChops
from test_scoreboard_app import scoreboard as core


@pytest.mark.parametrize('size',list(core.T9_SIZES))
@pytest.mark.parametrize('offset',[-100,0,20,100])
def test_portraits_never_cover_artwork(tmp_path,size,offset):
    photo=tmp_path/'portrait.png'
    Image.new('RGBA',(350,500),(255,0,150,190)).save(photo)
    cfg=copy.deepcopy(core.DEF_T9)
    cfg['canvas_size']=size
    baseline=core.render_t9(cfg)
    for side in ('a','b'):
        cfg['photo_'+side]=str(photo)
        cfg['photo_'+side+'_size_pct']=300
        cfg['photo_'+side+'_offset_x_pct']=offset
        cfg['photo_'+side+'_offset_y_pct']=offset
    rendered=core.render_t9(cfg)
    w,h=rendered.size
    difference=ImageChops.difference(baseline,rendered)
    assert difference.crop((0,int(h*.803),w,h)).getbbox() is None
    assert difference.crop((int(w*.305),0,int(w*.705),h)).getbbox() is None
    assert difference.crop((0,0,w,int(h*.068))).getbbox() is None
    if offset==0:
        assert difference.getbbox() is not None
        rendered.save(tmp_path/'head2head-clipped.png')


def test_footer_caption_editable():
    cfg=copy.deepcopy(core.DEF_T9)
    assert cfg['meeting']=='FIRST MEETING'
    baseline=core.render_t9(cfg)
    cfg['meeting']='SECOND MEETING'
    changed=core.render_t9(cfg)
    bbox=ImageChops.difference(baseline,changed).getbbox()
    assert bbox and bbox[1]>baseline.height*.803

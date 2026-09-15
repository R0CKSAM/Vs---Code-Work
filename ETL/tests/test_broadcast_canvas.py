from pathlib import Path

import pytest
from test_scoreboard_app import scoreboard


@pytest.mark.parametrize('template', scoreboard.WEB_TEMPLATE_KEYS)
@pytest.mark.parametrize('canvas,size', scoreboard.BROADCAST_SIZES.items())
def test_every_template_broadcast_size(template, canvas, size, tmp_path):
    config = scoreboard.normalise_project_configs({template:{'canvas_size':canvas}})[template]
    if template == 't8':
        source = tmp_path / 'portrait.png'
        scoreboard.Image.new('RGB',(100,200),'red').save(source)
        config['media_path'] = str(source)
    image = scoreboard.RENDERERS[template](config)
    assert image.size == size
    assert image.width * 9 == image.height * 16
    assert image.getextrema()[0][0] != image.getextrema()[0][1]
    if size == (1920,1080):
        image.save(tmp_path / (template+'.png'))


def test_old_aspect_ratio_migrates_without_mutating_saved_config():
    original = {'canvas_size':'Square(1080x1080)', 'score':'6-4'}
    updated = scoreboard.normalise_project_configs({'t3':original})['t3']
    assert updated['canvas_size'] == 'HD  (1920x1080)'
    assert updated['score'] == '6-4'
    assert original['canvas_size'] == 'Square(1080x1080)'


def test_uhd_mp4_is_separate_from_sdi_presets():
    command = scoreboard.build_mp4_command('ffmpeg',Path('in.png'),Path('out.mp4'),'UHD 2160p50',1)
    assert 'scale=3840:2160' in command[command.index('-vf')+1]
    assert command[command.index('-r')+1] == '50'
    assert 'UHD 2160p50' not in scoreboard.VIDEO_EXPORT_PRESETS

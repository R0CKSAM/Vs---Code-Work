import io
import threading

import pytest
from test_scoreboard_app import scoreboard, scoreboard_web


@pytest.mark.parametrize('template', scoreboard.WEB_TEMPLATE_KEYS)
def test_browser_cannot_supply_internal_render_scale(tmp_path, template):
    runtime = scoreboard_web.ScoreboardWebRuntime(scoreboard, tmp_path/'uploads')
    config = runtime.normalized_config(template, {'_render_scale': 1000000})
    assert '_render_scale' not in config


def test_program_snapshot_clear_ownership_and_stale_commands(tmp_path,monkeypatch):
    class Output:
        def __init__(self,*args): self.image=None; self.stopped=False
        def start(self,image): self.update(image)
        def update(self,image): self.image=image.copy()
        def snapshot_frame(self): return self.image.copy()
        def stop(self): self.stopped=True
        def poll_error(self): return None
    monkeypatch.setattr(scoreboard,'DeckLinkLiveOutput',Output)
    runtime=scoreboard_web.ScoreboardWebRuntime(scoreboard,tmp_path/'uploads')
    owner='owner-test'
    other='other-test'
    runtime.register_session(owner,'Operator','127.0.0.1')
    runtime.register_session(other,'Other','192.168.50.100')
    preset=next(iter(scoreboard.VIDEO_EXPORT_PRESETS))
    output_name=next(iter(scoreboard.DECKLINK_OUTPUTS))
    initial=runtime.start_live('t1',scoreboard.DEF_T1,preset,output_name,owner,'127.0.0.1',standby=True)
    assert initial['active'] and initial['on_air'] is None
    assert scoreboard.Image.open(io.BytesIO(runtime.program_preview()[0])).getbbox() is None
    shown=runtime.show_live('t1',scoreboard.DEF_T1,owner,'127.0.0.1',initial['program_revision'],'Opening')
    encoded,revision=runtime.program_preview()
    assert revision==shown['program_revision']
    assert scoreboard.Image.open(io.BytesIO(encoded)).getbbox() is not None
    runtime.render('t7',scoreboard.DEF_T7,update_live=False,client_id=owner)
    assert runtime.program_preview()[0]==encoded
    for action in (runtime.clear_live,):
        with pytest.raises(PermissionError): action(other,'192.168.50.100')
    with pytest.raises(scoreboard_web.ProjectConflict):
        runtime.clear_live(owner,'127.0.0.1',initial['program_revision'])
    with pytest.raises(scoreboard_web.ProjectConflict):
        runtime.show_live('t7',scoreboard.DEF_T7,owner,'127.0.0.1',initial['program_revision'])
    with pytest.raises(scoreboard_web.ProjectConflict):
        runtime.stop_live(owner,'127.0.0.1',expected_revision=initial['program_revision'])
    assert runtime.program_preview()[0]==encoded
    live_output=runtime.live_output
    cleared=runtime.clear_live(owner,'127.0.0.1',shown['program_revision'])
    assert cleared['active'] and cleared['on_air'] is None and not live_output.stopped
    assert scoreboard.Image.open(io.BytesIO(runtime.program_preview()[0])).getbbox() is None
    runtime.show_live('t7',scoreboard.DEF_T7,owner,'127.0.0.1',cleared['program_revision'])
    runtime.stop_live(force=True)
    assert live_output.stopped


def test_decklink_snapshot_uses_output_buffer():
    output=object.__new__(scoreboard.DeckLinkLiveOutput)
    output.preset_name=next(iter(scoreboard.VIDEO_EXPORT_PRESETS))
    output._frame_lock=threading.Lock()
    output._frame_data=b''
    output._set_frame(scoreboard.Image.new('RGB',(16,9),'red'))
    frame=output.snapshot_frame()
    assert frame.getpixel((0,0)) == (255,0,0)
    output._set_frame(scoreboard.Image.new('RGB',(16,9),'blue'))
    assert output.snapshot_frame().getpixel((0,0)) == (0,0,255)
    assert frame.getpixel((0,0)) == (255,0,0)

import pytest
from test_scoreboard_app import scoreboard as core, scoreboard_web as web


@pytest.mark.parametrize('mode,color',[('black',(0,0,0)),('chroma-green',(0,255,0)),('chroma-blue',(0,0,255))])
def test_clear_modes(tmp_path,monkeypatch,mode,color):
    runtime=web.ScoreboardWebRuntime(core,tmp_path/'uploads')
    assert runtime._clear_frame((10,10),mode).getpixel((0,0))==color
    runtime.live_clear_mode=mode
    runtime.live_preset='HD 1080i50'
    runtime.live_owner_id='operator'
    class Output:
        def update(self,image): self.image=image
    output=Output();runtime.live_output=output
    monkeypatch.setattr(runtime,'touch_session',lambda *args:dict(id='operator',priority=1))
    monkeypatch.setattr(runtime,'live_status',lambda *args:{})
    runtime.clear_live('operator','lan')
    assert runtime.live_output is output
    assert output.image.getpixel((100,100))==color
    assert runtime.on_air is None


def test_unconfirmed_and_unsupported_key_modes_rejected(tmp_path):
    runtime=web.ScoreboardWebRuntime(core,tmp_path/'uploads')
    sentinel=object();runtime.live_output=sentinel
    for mode in ('external','internal','invalid','chroma-green','chroma-blue'):
        with pytest.raises(ValueError):
            runtime.start_live('t1',core.DEF_T1,'HD 1080i50','SDI','operator','lan',clear_mode=mode)
        assert runtime.live_output is sentinel

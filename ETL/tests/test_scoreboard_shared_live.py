import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer

import pytest
from test_scoreboard_app import scoreboard, scoreboard_web


def test_atomic_save_notification_duplicates_and_restart(tmp_path,monkeypatch):
    runtime=scoreboard_web.ScoreboardWebRuntime(scoreboard,tmp_path/'uploads')
    revision=runtime.library_revision
    payload=dict(template='t9',player='One vs Two',country='India',config=scoreboard.DEF_T9)
    gate=threading.Barrier(2)
    def save():
        gate.wait(timeout=5)
        return runtime.save_template(payload,'192.168.50.10')
    with ThreadPoolExecutor(max_workers=3) as pool:
        changed=pool.submit(runtime.wait_for_library,revision,3)
        first,second=pool.submit(save),pool.submit(save)
        results=[first.result(timeout=5),second.result(timeout=5)]
        assert sum(result['saved'] for result in results)==1
        assert changed.result(timeout=5)['revision']!=revision
    assert len(runtime.list_templates())==1
    fresh=scoreboard_web.ScoreboardWebRuntime(scoreboard,tmp_path/'uploads')
    assert fresh.library_revision!=runtime.library_revision
    assert fresh.library_snapshot()['templates']==runtime.library_snapshot()['templates']
    old_revision=runtime.library_revision
    def fail_replace(*args):
        raise OSError('Disk unavailable')
    monkeypatch.setattr(scoreboard_web.os,'replace',fail_replace)
    with pytest.raises(OSError,match='Disk unavailable'):
        runtime.save_template({**payload,'player':'Failed save'},'192.168.50.10')
    assert runtime.library_revision==old_revision
    assert len(runtime.list_templates())==1
    assert not list(runtime.library_dir.glob('*.tmp'))


def test_corrupt_record_preserves_other_presets_and_source(tmp_path):
    runtime=scoreboard_web.ScoreboardWebRuntime(scoreboard,tmp_path/'uploads')
    payload=dict(template='t9',player='Valid',country='India',config=scoreboard.DEF_T9)
    runtime.save_template(payload,'127.0.0.1')
    broken=runtime.library_dir/('a'*32+'.json')
    broken.write_text('{partial',encoding='utf-8')
    snapshot=runtime.library_snapshot()
    assert len(snapshot['templates'])==1 and len(snapshot['warnings'])==1
    with pytest.raises(ValueError,match='host attention'):
        runtime.save_template({**payload,'player':'Another'},'127.0.0.1')
    assert broken.read_text()=='{partial'
    assert len(list(runtime.library_dir.glob('*.json')))==2


def test_two_browsers_instant_save_reconnect_without_changing_program(tmp_path,monkeypatch):
    from playwright.sync_api import sync_playwright,expect
    class Output:
        def __init__(self,*args): self.image=None
        def start(self,image): self.image=image.copy()
        def update(self,image): self.image=image.copy()
        def stop(self): pass
        def poll_error(self): return None
    monkeypatch.setattr(scoreboard,'DeckLinkLiveOutput',Output)
    runtime=scoreboard_web.ScoreboardWebRuntime(scoreboard,tmp_path/'uploads')
    monkeypatch.setattr(runtime,'output_capabilities',lambda:dict(devices=[
        dict(name=name,number=number,model='Test card',modes=list(scoreboard.VIDEO_EXPORT_PRESETS))
        for name,number in scoreboard.DECKLINK_OUTPUTS.items()]))
    server=ThreadingHTTPServer(('127.0.0.1',0),scoreboard_web.make_handler(runtime))
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch()
            creator=browser.new_page()
            operator=browser.new_page()
            errors=[]
            for page in (creator,operator):
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(f'http://127.0.0.1:{server.server_port}/scoreboard')
                page.click('#templateLabel');page.fill('#templateSearch','Head2Head')
                page.locator('#templateOptions button').click()
                expect(page.locator('#libraryStatus')).to_have_text('Library synced')
            operator.click('#liveButton');operator.wait_for_function('detectedOutputs.length>0')
            operator.check('#receiverConfirmed');operator.click('#startLive')
            expect(operator.locator('#liveDialog')).not_to_be_visible()
            operator.click('#takeLive')
            expect(operator.locator('#takeLive')).to_have_class('signal-green')
            program=runtime.program_preview()[0]
            operator.locator('[data-scalar=player_a]').fill('Operator unsaved draft')
            navigation=[]
            operator.on('framenavigated',lambda frame:navigation.append(frame.url))
            creator.locator('[data-scalar=player_a]').fill('New Player')
            creator.locator('[data-scalar=player_b]').fill('Opponent')
            creator.click('#savePreset')
            start=time.perf_counter()
            creator.click('#confirmPreset')
            expect(creator.locator('#presetDialog')).not_to_be_visible()
            expect(operator.locator('#presetPlayer')).to_contain_text('New Player vs Opponent',timeout=5000)
            elapsed=time.perf_counter()-start
            print(f'Creator-save to operator-library latency: {elapsed:.3f}s')
            assert elapsed<5
            expect(operator.locator('[data-scalar=player_a]')).to_have_value('Operator unsaved draft')
            assert runtime.program_preview()[0]==program
            # Missed notifications while offline are recovered without navigation.
            operator.context.set_offline(True)
            runtime.save_template(dict(template='t9',player='Saved while offline',country='Korea',config=scoreboard.DEF_T9),'192.168.50.11')
            operator.wait_for_timeout(300)
            operator.context.set_offline(False)
            expect(operator.locator('#presetPlayer')).to_contain_text('Saved while offline',timeout=15000)
            expect(operator.locator('#libraryStatus')).to_have_text('Library synced',timeout=15000)
            expect(operator.locator('[data-scalar=player_a]')).to_have_value('Operator unsaved draft')
            assert runtime.program_preview()[0]==program
            assert not navigation and not errors
            browser.close()
    finally:
        if runtime.live_output:
            runtime.live_output.stop()
        server.shutdown();server.server_close();thread.join(timeout=5)

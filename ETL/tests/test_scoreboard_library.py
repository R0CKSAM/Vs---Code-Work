import json
import threading
from http.server import ThreadingHTTPServer

import pytest
from test_scoreboard_app import scoreboard, scoreboard_web


def test_protected_template_update(tmp_path, monkeypatch):
    runtime = scoreboard_web.ScoreboardWebRuntime(scoreboard, tmp_path/'uploads')
    item = runtime.save_template(dict(template='t6', player='Player', country='India', config=scoreboard.DEF_T6), 'lan')['item']
    payload = dict(id=item['id'], edit_revision=item['edit_revision'], config={**item['config'], 'age':'28'}, username='veto', password='veto@spark')
    path = runtime.library_dir/(item['id']+'.json')
    original = path.read_bytes()
    with pytest.raises(ValueError, match='Incorrect'):
        runtime.update_template({**payload, 'password':'wrong'}, 'lan')
    assert path.read_bytes() == original
    changed = runtime.update_template(payload, 'lan')['item']
    assert changed['id'] == item['id'] and changed['config']['age'] == '28'
    assert changed['edit_revision'] != item['edit_revision']
    assert len(runtime.list_templates()) == 1
    assert next((runtime.library_dir/'history').glob('*.json')).read_bytes() == original
    with pytest.raises(scoreboard_web.ProjectConflict):
        runtime.update_template(payload, 'lan')
    before = path.read_bytes()
    def fail(*args): raise OSError('replace failed')
    monkeypatch.setattr(scoreboard_web.os, 'replace', fail)
    with pytest.raises(OSError):
        runtime.update_template({**payload, 'edit_revision':changed['edit_revision']}, 'lan')
    assert path.read_bytes() == before


def test_protected_legacy_update(tmp_path):
    runtime = scoreboard_web.ScoreboardWebRuntime(scoreboard,tmp_path/'uploads')
    identifier = 'a'*32
    document = dict(id=identifier, name='Legacy', revision=1, templates={'t6':scoreboard.DEF_T6, 't1':scoreboard.DEF_T1})
    path = runtime.project_dir/(identifier+'.json')
    path.write_text(json.dumps(document), encoding='utf-8')
    entries = runtime.list_templates()
    item = next(entry for entry in entries if entry['template']=='t6')
    other = next(entry for entry in entries if entry['template']=='t1')
    changed = runtime.update_template(dict(id=item['id'],edit_revision=item['edit_revision'],config={**item['config'],'age':'30'},username='veto',password='veto@spark'), 'lan')['item']
    assert changed['id']==item['id'] and changed['config']['age']=='30'
    assert other == next(entry for entry in runtime.list_templates() if entry['template']=='t1')
    assert json.loads(path.read_text())['revision']==2


def test_protected_update_browser(tmp_path):
    from playwright.sync_api import sync_playwright, expect
    runtime = scoreboard_web.ScoreboardWebRuntime(scoreboard,tmp_path/'uploads')
    item = runtime.save_template(dict(template='t6',player='Player',country='India',config=scoreboard.DEF_T6), 'lan')['item']
    server = ThreadingHTTPServer(('127.0.0.1',0),scoreboard_web.make_handler(runtime))
    thread = threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch()
            page=browser.new_page()
            errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.on('dialog',lambda dialog:dialog.accept())
            page.goto(f'http://127.0.0.1:{server.server_port}/scoreboard')
            page.click('#templateLabel')
            page.fill('#templateSearch','Players Stats')
            page.locator('#templateOptions button').click()
            page.click('#playerLabel')
            page.locator('#playerOptions button').filter(has_text='Player / India').click()
            page.locator('[data-scalar=age]').fill('28')
            page.click('#savePreset')
            expect(page.locator('#updateCredentials')).to_be_visible()
            page.fill('#editorUser','veto')
            page.fill('#editorPassword','wrong')
            page.click('#updatePreset')
            expect(page.locator('#presetError')).to_contain_text('Incorrect')
            page.fill('#editorPassword','veto@spark')
            page.click('#updatePreset')
            expect(page.locator('#presetDialog')).not_to_be_visible()
            assert runtime.list_templates()[0]['config']['age']=='28'
            assert not runtime.live_status()['active']
            assert not errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_flat_library_duplicate_and_portability(tmp_path):
    runtime = scoreboard_web.ScoreboardWebRuntime(scoreboard,tmp_path/'uploads')
    payload = dict(template='t6',player='Test Player',country='India',config=scoreboard.DEF_T6)
    first = runtime.save_template(payload,'192.168.50.10')
    assert first['saved']
    original = (runtime.library_dir/(first['item']['id']+'.json')).read_bytes()
    duplicate = runtime.save_template({**payload,'country':' INDIA ','player':'test player'},'192.168.50.11')
    assert not duplicate['saved']
    assert duplicate['existing']['id'] == first['item']['id']
    assert (runtime.library_dir/(first['item']['id']+'.json')).read_bytes() == original
    assert runtime.save_template({**payload,'country':'Korea'},'192.168.50.11')['saved']
    assert len(scoreboard_web.ScoreboardWebRuntime(scoreboard,tmp_path/'uploads').list_templates()) == 2
    with pytest.raises(ValueError):
        runtime.save_template({**payload,'country':''},'192.168.50.10')


def test_library_browser_and_live_controls(tmp_path,monkeypatch):
    from playwright.sync_api import sync_playwright, expect
    class Output:
        def __init__(self,*args): self.image=None
        def start(self,image): self.image=image.copy()
        def update(self,image): self.image=image.copy()
        def stop(self): pass
        def poll_error(self): return None
    monkeypatch.setattr(scoreboard,'DeckLinkLiveOutput',Output)
    runtime = scoreboard_web.ScoreboardWebRuntime(scoreboard,tmp_path/'uploads')
    server=ThreadingHTTPServer(('127.0.0.1',0),scoreboard_web.make_handler(runtime))
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch()
            page=browser.new_page(viewport={'width':1600,'height':1000})
            errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.on('dialog',lambda dialog:dialog.accept())
            page.goto(f'http://127.0.0.1:{server.server_port}/scoreboard')
            page.click('#templateLabel')
            page.fill('#templateSearch','Players Stats')
            page.locator('#templateOptions button').click()
            assert page.locator('#quickProject').count()==0
            page.locator('[data-scalar=player_name]').fill('Test Player')
            page.locator('[data-scalar=country]').fill('India')
            page.click('#savePreset')
            page.click('#confirmPreset')
            expect(page.locator('#presetDialog')).not_to_be_visible()
            expect(page.locator('#presetPlayer')).to_contain_text('Test Player')
            page.click('#savePreset')
            page.click('#confirmPreset')
            expect(page.locator('#viewDuplicate')).to_be_visible()
            page.click('#viewDuplicate')
            page.click('#newPlayer')
            page.locator('[data-scalar=player_name]').fill('Korea Player')
            page.locator('[data-scalar=country]').fill('Korea')
            page.click('#savePreset')
            page.click('#confirmPreset')
            expect(page.locator('#presetDialog')).not_to_be_visible()
            page.click('#countryLabel')
            page.locator('#countryOptions button').filter(has_text='India').click()
            expect(page.locator('#presetPlayer')).not_to_contain_text('Korea Player')
            page.click('#playerLabel')
            page.locator('#playerOptions button').filter(has_text='Test Player').click()
            page.click('#liveButton')
            page.click('#startLive')
            expect(page.locator('#liveDialog')).not_to_be_visible()
            assert runtime.live_output.image.getbbox() is None
            page.click('#takeLive')
            expect(page.locator('#takeLive')).to_have_class('signal-green')
            assert runtime.live_output.image.getbbox() is not None
            expect(page.locator('#programName')).to_have_text('Test Player')
            page.wait_for_function('document.getElementById("programImage").naturalWidth === 640')
            original_program=runtime.program_preview()[0]
            on_air=runtime.on_air
            page.locator('[data-scalar=age]').fill('28')
            expect(page.locator('#takeLive')).to_have_class('signal-yellow')
            assert runtime.on_air == on_air
            assert runtime.program_preview()[0] == original_program
            with pytest.raises(PermissionError):
                runtime.show_live('t6',scoreboard.DEF_T6,'other-client','192.168.50.21')
            page.click('#takeLive')
            expect(page.locator('#takeLive')).to_have_class('signal-green')
            assert runtime.program_preview()[0] != original_program
            assert page.locator('#takeLive').is_disabled()
            # Changing the layout loads preview only.
            current_program=runtime.program_preview()[0]
            page.click('#templateLabel')
            page.fill('#templateSearch','Qualifier')
            page.locator('#templateOptions button').click()
            assert runtime.program_preview()[0] == current_program
            page.click('#clearLive')
            expect(page.locator('#programState')).to_have_text('Black / Output running')
            assert runtime.live_status()['active']
            assert runtime.live_output.image.getbbox() is None
            assert page.locator('#clearLive').is_disabled()
            page.click('#takeLive')
            expect(page.locator('#programName')).to_have_text('Qualifier Rounds')
            page.screenshot(path=str(tmp_path/'library-desktop.png'),full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            page.screenshot(path=str(tmp_path/'library-mobile.png'),full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.click('#liveButton')
            expect(page.locator('#liveButton')).to_have_text('Start output')
            assert not runtime.live_status()['active']
            assert not errors
            browser.close()
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)

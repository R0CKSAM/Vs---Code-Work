import copy
import json
import threading
from http.server import ThreadingHTTPServer

import pytest
from test_scoreboard_app import scoreboard as core, scoreboard_web as web


def saved(runtime):
    return runtime.save_template(dict(template='t13',player='Bulletin',country='',
        config=copy.deepcopy(core.DEFAULT_CONFIGS['t13'])),'lan')['item']


def test_delete_auth_conflict_archive_and_program(tmp_path):
    runtime=web.ScoreboardWebRuntime(core,tmp_path/'uploads')
    item=saved(runtime)
    payload=dict(id=item['id'],edit_revision=item['edit_revision'],username='veto',password='bad')
    with pytest.raises(ValueError,match='Incorrect'):
        runtime.delete_template(payload,'lan')
    assert len(runtime.list_templates())==1
    payload['password']='spark@veto'
    with pytest.raises(web.ProjectConflict):
        runtime.delete_template(dict(payload,edit_revision='stale'),'lan')
    asset=runtime.upload_dir/'keep.png'
    asset.write_bytes(b'unchanged')
    program=object()
    runtime.program_frame=program
    revision=runtime.library_revision
    assert runtime.delete_template(payload,'lan')['deleted']
    assert runtime.program_frame is program
    assert runtime.library_revision!=revision
    assert not runtime.list_templates()
    assert asset.read_bytes()==b'unchanged'
    archive=list((runtime.library_dir/'deleted').glob('*.json'))
    assert len(archive)==1 and json.loads(archive[0].read_text())['id']==item['id']
    assert 'spark@veto' not in runtime.delete_credentials_path.read_text()
    with pytest.raises(web.ProjectConflict):
        runtime.delete_template(payload,'lan')


def test_delete_legacy_preserves_other_presets(tmp_path):
    runtime=web.ScoreboardWebRuntime(core,tmp_path/'uploads')
    identifier='a'*32
    document=dict(id=identifier,name='Legacy',revision=1,
                  templates={'t6':core.DEF_T6,'t1':core.DEF_T1})
    path=runtime.project_dir/(identifier+'.json')
    path.write_text(json.dumps(document),encoding='utf-8')
    original=path.read_bytes()
    entries=runtime.list_templates()
    item=next(p for p in entries if p['template']=='t6')
    other=next(p for p in entries if p['template']=='t1')
    runtime.delete_template(dict(id=item['id'],edit_revision=item['edit_revision'],
        username='veto',password='spark@veto'),'lan')
    assert runtime.list_templates()==[other]
    assert next((runtime.project_dir/'history').glob('*.json')).read_bytes()==original


def test_delete_browser(tmp_path):
    from playwright.sync_api import sync_playwright
    runtime=web.ScoreboardWebRuntime(core,tmp_path/'uploads')
    item=saved(runtime)
    server=ThreadingHTTPServer(('127.0.0.1',0),web.make_handler(runtime))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch()
            page=browser.new_page(viewport={'width':1600,'height':1000})
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(f'http://127.0.0.1:{server.server_port}/scoreboard')
            page.wait_for_function('previewReady && library.length===1')
            assert page.locator('#deletePreset').is_disabled()
            page.evaluate('(id)=>loadSaved(library.find(p=>p.id===id))',item['id'])
            page.click('#deletePreset')
            page.fill('#deleteUser','veto');page.fill('#deletePassword','bad')
            page.click('#confirmDelete')
            page.wait_for_function("document.getElementById('deleteError').textContent.includes('Incorrect')")
            assert len(runtime.list_templates())==1
            page.fill('#deletePassword','spark@veto')
            page.click('#confirmDelete')
            page.wait_for_function('library.length===0')
            assert page.locator('#deletePreset').is_disabled()
            assert page.evaluate('getConfig().headline')=='NEWS HEADLINE'
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            assert not errors
            browser.close()
    finally:
        server.shutdown();server.server_close()

import copy
import json
import threading
from http.server import ThreadingHTTPServer

from test_scoreboard_app import scoreboard, scoreboard_web


def test_head2head_fixed_rows_images_and_safe_text(tmp_path):
    config = scoreboard.normalise_project_configs({'t9':{
        'player_a':'A very long player name '*8, 'player_b':'Second Player',
        'country_a':'United States of America', 'rows':[None, {'label':'Age','value_a':27}],
    }})['t9']
    assert len(config['rows']) == 6
    assert config['rows'][1]['value_a'] == '27'
    original = copy.deepcopy(config)
    image = scoreboard.render_t9(config)
    assert image.size == (1920,1080)
    assert config == original
    photo = tmp_path/'player.png'
    scoreboard.Image.new('RGBA',(100,200),(240,20,180,255)).save(photo)
    config['photo_a'] = str(photo)
    pictured = scoreboard.render_t9(config)
    assert pictured.getpixel((300,600)) == (240,20,180)
    assert pictured.crop((610,400,1300,830)).tobytes() == image.crop((610,400,1300,830)).tobytes()
    pictured.save(tmp_path/'head2head-render.png')


def test_popup_cancel_discard_save_duplicate_and_switch(tmp_path):
    from playwright.sync_api import sync_playwright, expect
    runtime = scoreboard_web.ScoreboardWebRuntime(scoreboard,tmp_path/'uploads')
    saved = []
    for name in ('One','Two'):
        saved.append(runtime.save_template(dict(template='t9',player=name,country='India',
            config={**scoreboard.DEF_T9,'player_a':name,'player_b':'Opponent'}),'127.0.0.1')['item'])
    original = (runtime.library_dir/(saved[0]['id']+'.json')).read_bytes()
    server = ThreadingHTTPServer(('127.0.0.1',0),scoreboard_web.make_handler(runtime))
    thread = threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={'width':1600,'height':1000})
            errors, dialogs = [], []
            accept = [False]
            page.on('pageerror',lambda error:errors.append(str(error)))
            def dialog_handler(dialog):
                dialogs.append(dialog.message)
                dialog.accept() if accept[0] else dialog.dismiss()
            page.on('dialog',dialog_handler)
            page.goto(f'http://127.0.0.1:{server.server_port}/scoreboard')
            def choose(name):
                page.click('#templateLabel')
                page.fill('#templateSearch',name)
                page.locator('#templateOptions button').filter(has_text=name).first.click()
            choose('Head2Head')
            page.click('#playerLabel')
            page.locator('#playerOptions button').filter(has_text='One / India').click()
            expect(page.locator('[data-scalar=player_a]')).to_have_value('One')
            page.locator('[data-scalar=player_a]').fill('Edited')
            page.click('#playerLabel')
            page.locator('#playerOptions button').filter(has_text='Two / India').click()
            expect(page.locator('#presetPlayer')).to_have_value(saved[0]['id'])
            expect(page.locator('[data-scalar=player_a]')).to_have_value('Edited')
            assert len(dialogs) == 1
            choose('Head2Head')
            assert len(dialogs) == 1  # Selecting the active layout is a no-op.
            choose('Qualifier')
            expect(page.locator('#templateLabel')).to_have_text('Head2Head')
            accept[0] = True
            page.locator('#templateOptions button').click()
            expect(page.locator('#templateLabel')).to_have_text('Qualifier Rounds')
            choose('Head2Head')
            expect(page.locator('[data-scalar=player_a]')).to_have_value('One')
            assert (runtime.library_dir/(saved[0]['id']+'.json')).read_bytes() == original
            # Changing back to identical content is clean even with undo history.
            page.locator('[data-scalar=player_a]').fill('Temp')
            page.locator('[data-scalar=player_a]').fill('One')
            before = len(dialogs)
            choose('Qualifier')
            assert len(dialogs) == before
            choose('Head2Head')
            page.locator('[data-scalar=player_a]').fill('New Player')
            page.click('#savePreset')
            page.locator('#presetDialog [data-close]').click()
            expect(page.locator('[data-scalar=player_a]')).to_have_value('New Player')
            assert len(runtime.list_templates()) == 2
            page.click('#savePreset')
            page.fill('#presetPlayerName','One')
            page.click('#confirmPreset')
            expect(page.locator('#viewDuplicate')).to_be_visible()
            assert (runtime.library_dir/(saved[0]['id']+'.json')).read_bytes() == original
            page.fill('#presetPlayerName','New Player vs Opponent')
            page.click('#confirmPreset')
            expect(page.locator('#presetDialog')).not_to_be_visible()
            assert len(runtime.list_templates()) == 3
            before = len(dialogs)
            choose('Qualifier')
            assert len(dialogs) == before  # Successful save clears the dirty state.
            choose('Head2Head')
            expect(page.locator('[data-scalar=player_a]')).to_have_value('New Player')
            # Failed saves leave the draft dirty and restore usable controls.
            page.locator('[data-scalar=meeting]').fill('NEXT MEETING')
            page.route('**/api/templates/save',lambda route:route.fulfill(
                status=500,content_type='application/json',body='{"error":"Test storage failure"}'))
            page.click('#savePreset')
            page.click('#confirmPreset')
            expect(page.locator('#presetError')).to_have_text('Test storage failure')
            expect(page.locator('#confirmPreset')).to_be_enabled()
            page.locator('#presetDialog [data-close]').click()
            page.unroute('**/api/templates/save')
            accept[0] = False
            choose('Qualifier')
            expect(page.locator('#templateLabel')).to_have_text('Head2Head')
            page.locator('#templatePicker').evaluate('(el)=>el.open=false')
            # A pending upload cannot race a save or draft/template switch.
            photo = tmp_path/'browser-player.png'
            scoreboard.Image.new('RGBA',(20,40),(100,200,80,255)).save(photo)
            pending = []
            page.route('**/api/upload',lambda route:pending.append(route))
            page.locator('[data-upload=photo_a]').set_input_files(str(photo))
            expect(page.locator('#savePreset')).to_be_disabled()
            expect(page.locator('#newPlayer')).to_be_disabled()
            expect(page.locator('[data-scalar=player_a]')).to_be_disabled()
            page.wait_for_timeout(100)
            assert pending
            pending[0].fulfill(status=500,content_type='application/json',body='{"error":"Test upload failure"}')
            expect(page.locator('#savePreset')).to_be_enabled()
            expect(page.locator('[data-scalar=player_a]')).to_have_value('New Player')
            page.unroute('**/api/upload')
            page.wait_for_function('document.getElementById("preview").dataset.template==="t9" && document.getElementById("stage").getAttribute("aria-busy")==="false"')
            page.screenshot(path=str(tmp_path/'head2head-desktop.png'),full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            page.screenshot(path=str(tmp_path/'head2head-mobile.png'),full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert not errors
            browser.close()
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)

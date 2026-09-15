import threading
from http.server import ThreadingHTTPServer
from test_scoreboard_app import scoreboard,scoreboard_web


def test_search_filters_and_portrait_tools(tmp_path):
    from playwright.sync_api import sync_playwright, expect
    runtime=scoreboard_web.ScoreboardWebRuntime(scoreboard,tmp_path/'uploads')
    photo=runtime.upload_dir/'portrait.png'
    scoreboard.Image.new('RGBA',(100,200),(255,0,0,255)).save(photo)
    for country,name in [('India','India Player'),('Korea','Korea Player')]:
        runtime.save_template(dict(template='t6',player=name,country=country,config={**scoreboard.DEF_T6,'player_name':name,'country':country,'player_path':str(photo)}),'lan')
    server=ThreadingHTTPServer(('127.0.0.1',0),scoreboard_web.make_handler(runtime))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch();page=browser.new_page(viewport={'width':1600,'height':1000})
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(f'http://127.0.0.1:{server.server_port}/scoreboard')
            page.click('#templateLabel');page.fill('#templateSearch','Players Stats');page.locator('#templateOptions button').click()
            page.click('#playerLabel');page.fill('#playerSearch','Korea');page.locator('#playerOptions button').click()
            expect(page.locator('#countryLabel')).to_have_text('All countries')
            page.click('#playerLabel');expect(page.locator('#playerOptions')).to_contain_text('India Player')
            page.click('#countryLabel');page.fill('#countrySearch','India');page.locator('#countryOptions button').click()
            page.click('#playerLabel');expect(page.locator('#playerOptions')).not_to_contain_text('Korea Player')
            page.locator('#playerOptions button').filter(has_text='India Player').click()
            expect(page.locator('#countryLabel')).to_have_text('India')
            page.wait_for_function("document.querySelector('#stage').getAttribute('aria-busy')==='false'")
            page.click('#growImage');assert page.evaluate('getConfig().player_size_pct')==105
            page.click('#moveRight');assert page.evaluate('getConfig().player_offset_x_pct')==1
            expect(page.locator('[data-scalar="player_size_pct"]')).to_have_value('105')
            expect(page.locator('[data-scalar="player_offset_x_pct"]')).to_have_value('1')
            page.wait_for_function("document.querySelector('#stage').getAttribute('aria-busy')==='false'")
            box=page.locator('#preview').bounding_box()
            page.mouse.move(box['x']+box['width']*.3,box['y']+box['height']*.5)
            page.mouse.down();page.mouse.move(box['x']+box['width']*.4,box['y']+box['height']*.55);page.mouse.up()
            assert page.evaluate('getConfig().player_offset_x_pct')>5
            assert page.evaluate('getConfig().player_offset_y_pct')>0
            page.wait_for_function("document.querySelector('#stage').getAttribute('aria-busy')==='false' && document.querySelector('#preview').complete && document.querySelector('#preview').naturalWidth>0")
            for width in (320,390,768,1440):
                page.set_viewport_size({'width':width,'height':1000})
                page.click('#playerLabel')
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                popup=page.locator('#playerPicker .template-popup').bounding_box()
                assert popup['x']>=0 and popup['x']+popup['width']<=width
                page.screenshot(path=str(tmp_path/f'picker-{width}.png'),full_page=True)
                page.keyboard.press('Escape')
            assert not errors,errors
            assert not runtime.live_status()['active']
            browser.close()
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)


def test_portrait_transform_defaults_and_clamps():
    cfg=scoreboard.normalise_project_configs({'t6':{'player_offset_x_pct':999,'player_offset_y_pct':-999,'player_size_pct':999}})['t6']
    assert (cfg['player_offset_x_pct'],cfg['player_offset_y_pct'],cfg['player_size_pct'])==(100,-100,300)
    assert scoreboard.normalise_project_configs({})['t6']['player_size_pct']==100


def test_portrait_transform_changes_pixels_only_in_portrait_zone(tmp_path):
    from PIL import ImageChops
    photo=tmp_path/'red.png'
    scoreboard.Image.new('RGBA',(100,200),(255,0,0,255)).save(photo)
    cfg={**scoreboard.DEF_T6,'player_path':str(photo)}
    original=scoreboard.render_t6(cfg)
    moved=scoreboard.render_t6({**cfg,'player_offset_x_pct':10,'player_size_pct':75})
    assert ImageChops.difference(original,moved).getbbox()
    assert ImageChops.difference(original.crop((1200,0,1920,1080)),moved.crop((1200,0,1920,1080))).getbbox() is None

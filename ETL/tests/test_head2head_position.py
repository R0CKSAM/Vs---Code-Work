import threading
from http.server import ThreadingHTTPServer
from PIL import ImageChops
from test_scoreboard_app import scoreboard, scoreboard_web


def test_independent_portrait_render_and_persistence(tmp_path):
    photo=tmp_path/'portrait.png'
    scoreboard.Image.new('RGBA',(100,200),'red').save(photo)
    cfg={**scoreboard.DEF_T9,'photo_a':str(photo),'photo_b':str(photo)}
    original=scoreboard.render_t9(cfg)
    moved=scoreboard.render_t9({**cfg,'photo_a_offset_x_pct':5,'photo_a_size_pct':75})
    assert ImageChops.difference(original,moved).getbbox()
    assert ImageChops.difference(original.crop((1100,0,1920,1080)),moved.crop((1100,0,1920,1080))).getbbox() is None
    runtime=scoreboard_web.ScoreboardWebRuntime(scoreboard,tmp_path/'uploads')
    cfg.update(photo_a_size_pct=75,photo_b_offset_y_pct=-5)
    item=runtime.save_template(dict(template='t9',player='Pair',country='India',config=cfg),'lan')['item']
    assert item['config']['photo_a_size_pct']==75
    assert item['config']['photo_b_offset_y_pct']==-5
    restored=scoreboard_web.ScoreboardWebRuntime(scoreboard,tmp_path/'uploads')
    assert restored.list_templates()[0]['config']['photo_b_offset_y_pct']==-5


def test_browser_both_portraits(tmp_path):
    from playwright.sync_api import sync_playwright
    runtime=scoreboard_web.ScoreboardWebRuntime(scoreboard,tmp_path/'uploads')
    photo=runtime.upload_dir/'portrait.png'
    scoreboard.Image.new('RGBA',(100,200),'red').save(photo)
    server=ThreadingHTTPServer(('127.0.0.1',0),scoreboard_web.make_handler(runtime))
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch();page=browser.new_page(viewport={'width':1600,'height':1000})
            page.goto(f'http://127.0.0.1:{server.server_port}/scoreboard')
            page.wait_for_function('previewReady')
            page.click('#templateLabel');page.fill('#templateSearch','Head2Head');page.locator('#templateOptions button').click()
            page.evaluate('(path)=>{getConfig().photo_a=path;getConfig().photo_b=path;scheduleRender()}',str(photo))
            page.wait_for_function('previewReady')
            page.click('#growImage');page.click('#moveRight')
            assert page.evaluate('getConfig().photo_a_size_pct')==105
            assert page.evaluate('getConfig().photo_a_offset_x_pct')==1
            page.select_option('#previewLayer','photo_b')
            page.click('#shrinkImage');page.click('#moveUp')
            assert page.evaluate('getConfig().photo_b_size_pct')==95
            assert page.evaluate('getConfig().photo_b_offset_y_pct')==-1
            page.wait_for_function('previewReady')
            box=page.locator('#preview').bounding_box()
            page.mouse.move(box['x']+box['width']*.8,box['y']+box['height']*.5)
            page.mouse.down();page.mouse.move(box['x']+box['width']*.85,box['y']+box['height']*.5);page.mouse.up()
            assert page.evaluate('getConfig().photo_b_offset_x_pct')>4
            assert page.evaluate('getConfig().photo_a_offset_x_pct')==1
            page.wait_for_function('previewReady')
            page.screenshot(path=str(tmp_path/'h2h-position.png'))
            assert not runtime.live_status()['active']
            browser.close()
    finally:
        server.shutdown();server.server_close();worker.join(timeout=5)

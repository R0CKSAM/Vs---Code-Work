import copy
import threading
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from http.server import ThreadingHTTPServer

from PIL import Image, ImageChops
from test_scoreboard_app import scoreboard as core, scoreboard_web as web


def test_news_dynamic_geometry():
    spec=importlib.util.spec_from_file_location('news_layout_test',Path(core.__file__).with_name('scoreboard_match_templates.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    cfg=copy.deepcopy(core.DEFAULT_CONFIGS['t13'])
    c=SimpleNamespace(**vars(core))
    short=module.news_layout(c,cfg,1920,1080)
    cfg.update(headline='A longer headline with multiple words '*20,subject='A detailed report. '*150)
    long=module.news_layout(c,cfg,1920,1080)
    assert long[0][2]==short[0][2]
    assert long[0][3]>=short[0][3]
    assert long[1][1]>long[0][1]+long[0][3]
    assert long[1][1]+long[1][3]<=round(1080*.88)
    cfg.update(auto_text_height=False,headline_height_pct=12,subject_height_pct=30)
    manual=module.news_layout(c,cfg,1920,1080)
    assert manual[0][3]==round(1080*.12)
    assert manual[1][3]==round(1080*.30)


def test_news_save_and_render(tmp_path):
    runtime=web.ScoreboardWebRuntime(core,tmp_path/'uploads')
    cfg=copy.deepcopy(core.DEFAULT_CONFIGS['t13'])
    first=runtime.render('t13',cfg)[0]
    cfg.update(headline='Breaking news',subject='A detailed report. '*80,
               headline_box_color=[150,20,30])
    second=runtime.render('t13',cfg)[0]
    assert ImageChops.difference(first,second).getbbox()
    saved=runtime.save_template(dict(template='t13',player='Evening news',country='',config=cfg),'lan')
    assert saved['saved']
    reopened=runtime.list_templates()[0]
    assert reopened['config']['subject']==cfg['subject']
    assert reopened['country']==''
    cfg['logo_path']=''
    cfg['show_logo']=False
    hidden=runtime.render('t13',cfg)[0]
    cfg['show_logo']=True
    visible=runtime.render('t13',cfg)[0]
    assert ImageChops.difference(hidden,visible).getbbox()
    if core._load_pango_modules():
        cfg.update(headline='भारत की ताज़ा खबर',subject='यह समाचार का विवरण है।\nالعربية الأخبار')
        assert runtime.render('t13',cfg)[0].size==(1920,1080)


def test_news_browser(tmp_path):
    from playwright.sync_api import sync_playwright
    runtime=web.ScoreboardWebRuntime(core,tmp_path/'uploads')
    server=ThreadingHTTPServer(('127.0.0.1',0),web.make_handler(runtime))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    photo=tmp_path/'photo.png'
    Image.new('RGB',(300,400),'red').save(photo)
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch()
            page=browser.new_page(viewport={'width':1600,'height':1000})
            errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(f'http://127.0.0.1:{server.server_port}/scoreboard')
            page.wait_for_function('previewReady')
            page.click('#templateLabel')
            page.fill('#templateSearch','News Headline')
            page.locator('#templateOptions button').click()
            page.wait_for_function("template==='t13' && previewReady")
            page.locator('[data-scalar="headline"]').fill('News headline')
            page.locator('[data-scalar="subject"]').fill('A detailed report with independently styled text.')
            page.locator('input[data-upload="image_path"]').set_input_files(str(photo))
            page.wait_for_function('getConfig().image_path && previewReady')
            assert page.evaluate('moveTarget().size')=='image_size_pct'
            page.select_option('#textRole','headline')
            page.wait_for_selector('#textSize')
            page.locator('#textSize').fill('110')
            page.locator('#textSize').dispatch_event('input')
            page.click('#savePreset')
            page.locator('#presetPlayerName').fill('Evening news')
            page.click('#confirmPreset')
            page.wait_for_function('library.some(p=>p.player==="Evening news")')
            page.screenshot(path=str(tmp_path/'news-desktop.png'))
            page.set_viewport_size({'width':390,'height':844})
            page.screenshot(path=str(tmp_path/'news-mobile.png'))
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            assert not errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()

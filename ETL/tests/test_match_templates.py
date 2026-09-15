import copy
import threading
from http.server import ThreadingHTTPServer

import pytest
from PIL import ImageChops
from test_scoreboard_app import scoreboard as core, scoreboard_web as web


@pytest.mark.parametrize('key',['t10','t11','t12'])
def test_new_template_roundtrip(key,tmp_path):
    runtime=web.ScoreboardWebRuntime(core,tmp_path/'uploads')
    cfg=copy.deepcopy(core.DEFAULT_CONFIGS[key])
    first=runtime.render(key,cfg)[0]
    cfg['country_a']='Brazil'
    cfg['title']='Editable title'
    second=runtime.render(key,cfg)[0]
    assert ImageChops.difference(first,second).getbbox()
    saved=runtime.save_template(dict(template=key,player='Match',country='Brazil',config=cfg),'lan')
    reopened=web.ScoreboardWebRuntime(core,tmp_path/'uploads').list_templates()[0]
    assert saved['saved'] and reopened['config']['title']=='Editable title'
    assert not runtime.live_status()['active']


def test_output_rejects_unsupported_before_touching_live(tmp_path,monkeypatch):
    runtime=web.ScoreboardWebRuntime(core,tmp_path/'uploads')
    monkeypatch.setattr(runtime,'output_capabilities',lambda:dict(devices=[
        dict(name='SDI',number=0,modes=['HD 1080i50'])]))
    sentinel=object()
    runtime.live_output=sentinel
    with pytest.raises(ValueError,match='not supported'):
        runtime.start_live('t1',core.DEF_T1,'UHD 2160p60','SDI','test','lan')
    assert runtime.live_output is sentinel


def test_fractional_pipeline_and_export():
    pipeline=core.build_decklink_pipeline('HD 1080i59.94',0)
    assert 'framerate=30000/1001' in pipeline
    assert 'interlace-mode=interleaved' in pipeline
    cmd=core.build_mp4_command('ffmpeg','input.png','output.mp4','HD 1080p59.94',1)
    assert cmd[cmd.index('-r')+1]=='60000/1001'
    assert cmd[cmd.index('-g')+1]=='120'


def test_browser_new_templates_and_cross_country(tmp_path,monkeypatch):
    from playwright.sync_api import sync_playwright
    runtime=web.ScoreboardWebRuntime(core,tmp_path/'uploads')
    monkeypatch.setattr(runtime,'output_capabilities',lambda:dict(devices=[
        dict(name='SDI',model='Test HD card',number=0,modes=['HD 1080i50','HD 720p60'])]))
    for name,country,age in [('One','India','24'),('Two','Korea','30')]:
        cfg=dict(core.DEF_T6,player_name=name,country=country,age=age,total_wl='2/1',
                 atp_ranking='100',season_year='2026',season_wl='5/2',career_high='80')
        runtime.save_template(dict(template='t6',player=name,country=country,config=cfg),'lan')
    server=ThreadingHTTPServer(('127.0.0.1',0),web.make_handler(runtime))
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch()
            page=browser.new_page(viewport={'width':1600,'height':1000})
            errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}/scoreboard')
            page.wait_for_function('previewReady && library.length===2')
            for title,key in [('Match Day','t10'),('Coming Next','t11'),('Quarter Finals','t12'),('Head2Head','t9')]:
                page.evaluate('()=>{window.confirm=()=>true}')
                page.click('#templateLabel');page.fill('#templateSearch',title)
                page.locator('#templateOptions button').click()
                page.wait_for_function('(key)=>template===key && previewReady',arg=key)
                assert page.locator('#preview').evaluate('(el)=>el.naturalWidth')==1920
                if key in ('t9','t10'):
                    for side,country in [('a','India'),('b','Korea')]:
                        page.select_option(f'[data-roster-country="{side}"]',country)
                        select=page.locator(f'[data-roster-player="{side}"]')
                        select.select_option(index=1)
                    assert page.evaluate('getConfig().player_a')=='One'
                    assert page.evaluate('getConfig().player_b')=='Two'
                    if key=='t9':
                        assert page.evaluate('getConfig().rows[1].value_a')=='24'
                        assert page.evaluate('getConfig().rows[0].value_a')=='100'
                        assert page.evaluate('getConfig().rows[2].value_b')=='5/2'
                        assert page.evaluate('getConfig().rows[5].value_b')==''
                page.wait_for_function('previewReady')
                page.screenshot(path=str(tmp_path/(key+'-desktop.png')))
            page.click('#liveButton')
            page.wait_for_function('detectedOutputs.length===1')
            page.select_option('#clearMode','chroma-blue')
            assert page.locator('#keyerConfirmation').is_visible()
            assert not page.locator('#keyerConfirmed').is_checked()
            page.check('#keyerConfirmed')
            page.select_option('#clearMode','chroma-green')
            assert not page.locator('#keyerConfirmed').is_checked()
            page.select_option('#clearMode','black')
            assert page.locator('#livePreset option').count()==2
            assert page.locator('#livePreset').input_value()=='HD 1080i50'
            assert page.locator('#startLive').is_disabled()
            page.check('#receiverConfirmed')
            assert page.locator('#startLive').is_enabled()
            page.select_option('#livePreset','HD 720p60')
            assert page.locator('#startLive').is_disabled()
            page.click('[data-close="liveDialog"]')
            page.set_viewport_size({'width':390,'height':844})
            page.screenshot(path=str(tmp_path/'mobile.png'))
            assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
            assert not errors
            browser.close()
    finally:
        server.shutdown();server.server_close();worker.join(timeout=5)

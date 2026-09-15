import threading
from http.server import ThreadingHTTPServer

from test_scoreboard_app import scoreboard, scoreboard_web


def test_qualifier_country_flags_and_normalization(monkeypatch):
    assert scoreboard.qualifier_country_code('  Korea ') == 'kr'
    assert scoreboard.qualifier_country_code('INDIA') == 'in'
    assert scoreboard.qualifier_country_code('South Korea') == 'kr'
    assert scoreboard.qualifier_country_code('Atlantis') is None
    assert len(scoreboard.QUALIFIER_ALPHA3) == 249
    for name,code in [('India','IND'),('Korea','KOR'),('United States of America','USA'),
                      ('United Kingdom','GBR'),('South Africa','ZAF'),('Germany','DEU')]:
        assert scoreboard.qualifier_country_label(name) == code
        assert scoreboard.qualifier_country_label(code.lower()) == code
    assert scoreboard.qualifier_country_label('Atlantis') == '---'
    assert scoreboard.qualifier_country_label('') == '---'
    config = scoreboard.normalise_project_configs({'t7':{'rows':None}})['t7']
    assert len(config['rows']) == 5
    image = scoreboard.render_t7(config)
    assert image.size == (1920,1080)
    assert image.getextrema()[0][0] < image.getextrema()[0][1]
    config['country_a'] = 'United States of America'
    config['rows'][0]['value_a'] = 'An exceptionally long doubles pairing / second player'
    assert scoreboard.render_t7(config).size == image.size
    drawn = []
    original = scoreboard.draw_text_centered
    def capture(draw,text,*args,**kwargs):
        drawn.append(text)
        return original(draw,text,*args,**kwargs)
    monkeypatch.setattr(scoreboard,'draw_text_centered',capture)
    scoreboard.render_t7(config)
    assert drawn.count('USA') == 2
    assert drawn.count('KOR') == 2
    assert 'UNITED STATES OF AMERICA' not in drawn
    import zipfile
    from pathlib import Path
    with zipfile.ZipFile(Path(scoreboard.__file__).with_name('country_flags.zip')) as archive:
        assert all(code+'.png' in archive.namelist() for code in scoreboard.QUALIFIER_ALPHA3)


def test_qualifier_browser(tmp_path):
    from playwright.sync_api import sync_playwright, expect
    runtime = scoreboard_web.ScoreboardWebRuntime(scoreboard, tmp_path/'uploads')
    server = ThreadingHTTPServer(('127.0.0.1',0),scoreboard_web.make_handler(runtime))
    thread = threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={'width':1600,'height':1000})
            errors = []
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}/scoreboard')
            page.locator('#template option[value=t7]').wait_for(state='attached')
            page.click('#templateLabel')
            page.fill('#templateSearch','Qualifier')
            page.locator('#templateOptions button').click()
            assert page.locator('[data-row-field]').count() == 10
            page.locator('[data-scalar=country_a]').fill('India')
            page.locator('[data-scalar=country_b]').fill('Korea')
            page.locator('[data-row-field=value_a]').first.select_option('W')
            page.locator('[data-row-field=value_b]').first.select_option('L')
            assert page.evaluate('getConfig().rows[0]')=={'value_a':'W','value_b':'L'}
            expect(page.locator('.preview-tools')).to_be_hidden()
            page.wait_for_timeout(1800)
            assert page.locator('#preview').evaluate('(img)=>img.naturalWidth') == 1920
            page.screenshot(path=str(tmp_path/'qualifier-desktop.png'),full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            page.screenshot(path=str(tmp_path/'qualifier-mobile.png'),full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert not errors
            assert not runtime.live_status()['active']
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

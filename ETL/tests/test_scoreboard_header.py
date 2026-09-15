import threading
from http.server import ThreadingHTTPServer

import pytest
from test_scoreboard_app import scoreboard,scoreboard_web


def test_visible_header_layout_and_host_stop(tmp_path,monkeypatch):
    from playwright.sync_api import sync_playwright,expect
    class Output:
        def __init__(self,*args): self.image=None
        def start(self,image): self.image=image.copy()
        def update(self,image): self.image=image.copy()
        def stop(self): pass
        def poll_error(self): return None
    monkeypatch.setattr(scoreboard,'DeckLinkLiveOutput',Output)
    runtime=scoreboard_web.ScoreboardWebRuntime(scoreboard,tmp_path/'uploads')
    runtime.register_session('lan-owner','LAN Playout','192.168.50.11')
    runtime.start_live('t9',scoreboard.DEF_T9,next(iter(scoreboard.VIDEO_EXPORT_PRESETS)),
        next(iter(scoreboard.DECKLINK_OUTPUTS)),'lan-owner','192.168.50.11',standby=True)
    server=ThreadingHTTPServer(('127.0.0.1',0),scoreboard_web.make_handler(runtime))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch()
            page=browser.new_page(viewport={'width':1600,'height':1000})
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(f'http://127.0.0.1:{server.server_port}/scoreboard')
            expect(page.locator('#accessRole')).to_have_text('Host control')
            ids=['countryLabel','playerLabel','newPlayer','savePreset','operatorName',
                 'usersButton','mp4Button','pngButton','reset','liveButton','takeLive','clearLive']
            assert page.locator('.operator-menu').count()==0
            for width in (320,390,768,1024,1440,1920):
                page.set_viewport_size({'width':width,'height':1000})
                for key in ids:
                    expect(page.locator('header #'+key)).to_be_visible()
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                boxes=[page.locator('#'+key).bounding_box() for key in ids]
                for i,a in enumerate(boxes):
                    assert a['x']>=0 and a['x']+a['width']<=width+1
                    for b in boxes[i+1:]:
                        overlap_x=min(a['x']+a['width'],b['x']+b['width'])-max(a['x'],b['x'])
                        overlap_y=min(a['y']+a['height'],b['y']+b['height'])-max(a['y'],b['y'])
                        assert overlap_x<=1 or overlap_y<=1
                if width in (390,1440):
                    page.screenshot(path=str(tmp_path/f'header-{width}.png'),full_page=True)
            page.click('#mp4Button');expect(page.locator('#mp4Dialog')).to_be_visible()
            page.locator('#mp4Dialog [data-close]').click()
            page.click('#usersButton');expect(page.locator('#usersDialog')).to_be_visible()
            page.locator('#usersDialog [data-close]').click()
            expect(page.locator('#liveButton')).to_have_text('Stop output')
            expect(page.locator('#takeLive')).to_be_disabled()
            # A different LAN client cannot stop this owner; host can, after confirmation.
            with pytest.raises(PermissionError):
                runtime.stop_live('other-lan','192.168.50.12')
            page.once('dialog',lambda d:d.dismiss());page.click('#liveButton')
            assert runtime.live_status()['active']
            page.once('dialog',lambda d:d.accept());page.click('#liveButton')
            expect(page.locator('#liveButton')).to_have_text('Start output')
            assert not runtime.live_status()['active']
            assert not errors
            browser.close()
    finally:
        if runtime.live_output: runtime.live_output.stop()
        server.shutdown();server.server_close();thread.join(timeout=5)

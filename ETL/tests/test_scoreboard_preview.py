import io
import threading
from http.server import ThreadingHTTPServer

from test_scoreboard_app import scoreboard, scoreboard_web


def test_preview_retains_frame_rejects_stale_results_and_recovers(tmp_path):
    from playwright.sync_api import sync_playwright, expect
    runtime=scoreboard_web.ScoreboardWebRuntime(scoreboard,tmp_path/'uploads')
    server=ThreadingHTTPServer(('127.0.0.1',0),scoreboard_web.make_handler(runtime))
    worker=threading.Thread(target=server.serve_forever,daemon=True)
    worker.start()
    data=io.BytesIO()
    scoreboard.Image.new('RGB',(160,90),'red').save(data,format='PNG')
    red=data.getvalue()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch()
            page=browser.new_page(viewport={'width':1440,'height':1000})
            errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(f'http://127.0.0.1:{server.server_port}/scoreboard')
            page.wait_for_function('previewReady && document.querySelector("#preview").complete')
            original=page.locator('#preview').get_attribute('src')
            pending=[]
            page.route('**/api/render',lambda route:pending.append(route))

            def change(title):
                page.evaluate('(title)=>{getConfig().title=title;scheduleRender()}',title)

            def wait_request(count):
                for _ in range(100):
                    if len(pending)>=count:
                        return
                    page.wait_for_timeout(30)
                raise AssertionError('Missing render request')

            def retained(url):
                assert page.locator('#preview').get_attribute('src')==url
                assert page.locator('#preview').evaluate("el=>getComputedStyle(el).visibility==='visible' && el.complete && el.naturalWidth>0")
                assert not page.evaluate('previewReady')
                expect(page.locator('#takeLive')).to_be_disabled()

            change('older edit');wait_request(1);retained(original)
            change('latest edit');wait_request(2);retained(original)
            # The newer response wins even if an older request finishes afterwards.
            pending[1].fulfill(status=200,content_type='image/png',body=red)
            page.wait_for_function('previewReady')
            latest=page.locator('#preview').get_attribute('src')
            assert latest!=original
            pending[0].fulfill(status=200,content_type='image/png',body=red)
            page.wait_for_timeout(150)
            assert page.locator('#preview').get_attribute('src')==latest

            change('failed edit');wait_request(3);retained(latest)
            pending[2].fulfill(status=200,content_type='image/png',body=b'corrupt image')
            expect(page.locator('#dimensions')).to_have_text('Update failed - previous preview')
            retained(latest)
            # A failed identical draft can be retried without changing its contents.
            page.evaluate('scheduleRender()');wait_request(4)
            pending[3].fulfill(status=200,content_type='image/png',body=red)
            page.wait_for_function('previewReady')
            assert page.locator('#preview').evaluate('el=>el.complete && el.naturalWidth===160')
            page.screenshot(path=str(tmp_path/'retained-preview.png'))
            assert not errors,errors
            assert not runtime.live_status()['active']
            browser.close()
    finally:
        server.shutdown();server.server_close();worker.join(timeout=5)

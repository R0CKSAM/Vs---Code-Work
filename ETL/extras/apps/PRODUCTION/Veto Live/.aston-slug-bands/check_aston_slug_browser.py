from http.server import ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading

from playwright.sync_api import sync_playwright,expect

import scoreboard_app as core
from scoreboard_web import ScoreboardWebRuntime,make_handler


with tempfile.TemporaryDirectory(dir=Path(__file__).parent,ignore_cleanup_errors=True) as directory:
    runtime=ScoreboardWebRuntime(core,Path(directory)/'uploads')
    server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(runtime))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(channel='chrome',headless=True)
            page=browser.new_page(viewport={'width':1440,'height':1000})
            errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            page.on('dialog',lambda dialog:dialog.accept())
            page.goto(f'http://127.0.0.1:{server.server_port}/scoreboard')
            page.wait_for_function("typeof boot !== 'undefined' && boot")
            page.evaluate("switchTemplate('t16')")
            page.wait_for_function("template==='t16' && previewReady")
            page.locator('[data-scalar="text_a"]').fill('भारत')
            page.locator('[data-scalar="text_b"]').fill('البث المباشر')
            page.wait_for_function("previewReady && configs.t16.text_a==='भारत'")
            expect(page.locator('#template option:checked')).to_have_text('Aston Band')
            page.screenshot(path=str(Path(__file__).with_name('aston-band-editor.png')),full_page=True)
            page.evaluate("switchTemplate('t17')")
            page.wait_for_function("template==='t17' && previewReady")
            page.locator('[data-scalar="text"]').fill('라이브 경기')
            page.wait_for_function("previewReady && configs.t17.text==='라이브 경기'")
            expect(page.locator('#template option:checked')).to_have_text('Slug Band')
            page.set_viewport_size({'width':390,'height':844})
            expect(page.locator('#preview')).to_be_visible()
            page.screenshot(path=str(Path(__file__).with_name('slug-band-mobile.png')),full_page=True)
            assert not errors,errors
            print({'aston_band':True,'slug_band':True,'unicode_text':True,'browser_errors':errors})
            browser.close()
    finally:
        runtime.stop_live(force=True);server.shutdown();server.server_close();thread.join()

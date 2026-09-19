from http.server import ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading

from playwright.sync_api import sync_playwright, expect

import scoreboard_app as core
from scoreboard_web import ScoreboardWebRuntime, make_handler


with tempfile.TemporaryDirectory(dir=Path(__file__).parent, ignore_cleanup_errors=True) as directory:
    runtime = ScoreboardWebRuntime(core, Path(directory) / 'uploads')
    server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(runtime))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel='chrome', headless=True)
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            errors=[]
            page.on('pageerror',lambda error: errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}/scoreboard')
            page.wait_for_function("typeof boot !== 'undefined' && boot")
            page.evaluate("switchTemplate('t15')")
            page.wait_for_function("template==='t15' && previewReady")
            expect(page.locator('#template option:checked')).to_have_text('Custom Band')
            expect(page.locator('[data-upload="band_path"]')).to_have_count(1)
            page.locator('[data-upload="band_path"]').set_input_files(
                str(Path(__file__).with_name('custom-band-preview.png')))
            page.wait_for_function("previewReady && !!configs.t15.band_path")
            page.locator('[data-scalar="band_size_pct"]').fill('125')
            page.locator('[data-scalar="band_size_pct"]').press('Enter')
            page.wait_for_function("previewReady && configs.t15.band_size_pct===125")
            page.screenshot(path=str(Path(__file__).with_name('custom-band-editor.png')),full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            expect(page.locator('#preview')).to_be_visible()
            page.screenshot(path=str(Path(__file__).with_name('custom-band-mobile.png')),full_page=True)
            assert not errors,errors
            print({'custom_band_upload':True,'move_resize_controls':True,'browser_errors':errors})
            browser.close()
    finally:
        runtime.stop_live(force=True)
        server.shutdown()
        server.server_close()
        thread.join()

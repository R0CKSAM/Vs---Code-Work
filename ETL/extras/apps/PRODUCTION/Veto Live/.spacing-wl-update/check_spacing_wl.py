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
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}/scoreboard')
            page.wait_for_function("typeof boot !== 'undefined' && boot")
            page.evaluate("switchTemplate('t11')")
            page.wait_for_function("template==='t11' && previewReady && document.querySelector('#preview').dataset.template==='t11'")
            expect(page.locator('[data-scalar="title_box_opacity_pct"]')).to_have_value('100')
            expect(page.locator('[data-color="title_box_color"]')).to_have_count(1)
            page.evaluate("switchTemplate('t5')")
            page.wait_for_function("template==='t5' && previewReady && document.querySelector('#preview').dataset.template==='t5'")
            expect(page.locator('label', has_text='W/L')).to_be_visible()
            page.screenshot(path=str(Path(__file__).with_name('spacing-wl-editor.png')), full_page=True)
            assert not errors, errors
            print({'coming_next_spacing': True, 'player_band_wl': True, 'browser_errors': errors})
            browser.close()
    finally:
        runtime.stop_live(force=True)
        server.shutdown()
        server.server_close()
        thread.join()

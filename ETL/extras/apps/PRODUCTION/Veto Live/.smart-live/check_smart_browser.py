from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
from unittest.mock import patch

from playwright.sync_api import sync_playwright, expect
import scoreboard_app as core
from scoreboard_web import ScoreboardWebRuntime, make_handler
from test_smart_live import RecordingOutput


with tempfile.TemporaryDirectory(dir=Path(__file__).parent, ignore_cleanup_errors=True) as directory:
    runtime = ScoreboardWebRuntime(core, Path(directory) / 'uploads')
    media = runtime.upload_dir / 'browser-smart-live.png'
    core.Image.new('RGB', (320, 180), (12, 60, 90)).save(media)
    media.with_suffix('.media.json').write_text(json.dumps({'kind': 'image', 'poster': ''}), encoding='utf-8')
    server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(runtime))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with patch.object(core, 'DeckLinkLiveOutput', RecordingOutput), sync_playwright() as p:
            browser = p.chromium.launch(channel='chrome', headless=True)
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            errors, scans = [], []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('request', lambda request: scans.append(request.url)
                    if '/api/output/capabilities' in request.url else None)
            page.on('dialog', lambda dialog: dialog.accept())
            page.goto(f'http://127.0.0.1:{server.server_port}/scoreboard')
            page.wait_for_function("typeof boot !== 'undefined' && boot && !!document.querySelector('#editor').children.length")
            for mode in ('external-key', 'chroma-magenta'):
                page.locator('#liveButton').click()
                page.locator('#clearMode').select_option(mode)
                page.locator('#receiverConfirmed').check()
                page.locator('#keyerConfirmed').check()
                page.locator('#startLive').click()
                expect(page.locator('#liveDialog')).not_to_be_visible()
                output = runtime.live_output
                instances = len(RecordingOutput.instances)
                for template in core.WEB_TEMPLATE_KEYS:
                    page.evaluate("([key,path])=>{switchTemplate(key);if(key==='t8'){configs.t8.media_path=path;configs.t8.media_kind='image';scheduleRender(false)}}", [template, str(media)])
                    page.wait_for_function("previewReady && document.querySelector('#preview').dataset.template===template")
                    expect(page.locator('#takeLive')).to_be_enabled(timeout=15000)
                    page.locator('#takeLive').click()
                    page.wait_for_function("!liveCommandBusy && latestLive.on_air && latestLive.program_name===boot.template_names[template]")
                    assert runtime.live_output is output
                    assert output.stop_count == 0
                assert len(RecordingOutput.instances) == instances
                page.screenshot(path=str(Path(__file__).with_name(f'smart-live-{mode}.png')))
                page.locator('#liveButton').click()
                expect(page.locator('#liveStatus')).to_have_text('Output stopped')
            assert not scans, scans
            assert not errors, errors
            print(json.dumps({'templates_per_mode': len(core.WEB_TEMPLATE_KEYS),
                              'modes': ['Fill + Key alpha', 'Magenta chroma'],
                              'pipeline_restarts_during_push': 0,
                              'scan_requests': 0, 'browser_errors': errors}))
            browser.close()
    finally:
        runtime.stop_live(force=True)
        server.shutdown()
        server.server_close()
        thread.join()

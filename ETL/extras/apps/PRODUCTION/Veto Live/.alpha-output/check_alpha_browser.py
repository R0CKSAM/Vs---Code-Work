from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
from unittest.mock import patch

from playwright.sync_api import sync_playwright, expect
import scoreboard_app as core
from scoreboard_web import ScoreboardWebRuntime, make_handler
from test_alpha_output import MemoryOutput


with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
    runtime = ScoreboardWebRuntime(core, Path(directory) / 'uploads')
    server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(runtime))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with patch.object(core, 'DeckLinkLiveOutput', MemoryOutput), sync_playwright() as p:
            browser = p.chromium.launch(channel='chrome', headless=True)
            for width, height in ((1440, 1000), (390, 844)):
                page = browser.new_page(viewport={'width': width, 'height': height})
                errors, scans = [], []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.on('request', lambda request: scans.append(request.url) if '/api/output/capabilities' in request.url else None)
                page.on('dialog', lambda dialog: dialog.accept())
                page.goto(f'http://127.0.0.1:{server.server_port}/scoreboard')
                page.wait_for_function("typeof boot !== 'undefined' && boot && !!document.querySelector('#editor').children.length")
                page.evaluate("template='t5';buildEditor();scheduleRender(false)")
                page.wait_for_function('previewReady')
                page.locator('#liveButton').click()
                expect(page.locator('#clearMode')).to_have_value('external-key')
                assert page.locator('#liveDevice option').count() == 2
                expect(page.locator('#livePreset')).to_have_value('HD 1080i50')
                expect(page.locator('#outputHardwareStatus')).to_contain_text('SDI 1 key / SDI 2 fill')
                expect(page.locator('#startLive')).to_be_disabled()
                page.locator('#receiverConfirmed').check()
                expect(page.locator('#startLive')).to_be_disabled()
                page.locator('#keyerConfirmed').check()
                expect(page.locator('#startLive')).to_be_enabled()
                page.screenshot(path=str(Path(__file__).with_name(f'alpha-ports-{width}.png')))
                page.locator('#startLive').click()
                expect(page.locator('#liveDialog')).not_to_be_visible()
                expect(page.locator('#liveStatus')).to_have_text('Transparent / Output running')
                expect(page.locator('#takeLive')).to_be_enabled(timeout=15000)
                page.locator('#takeLive').click()
                expect(page.locator('#liveStatus')).to_have_text('On Air')
                page.wait_for_function('programReady && displayedProgramRevision === latestLive.program_revision')
                page.screenshot(path=str(Path(__file__).with_name(f'alpha-on-air-{width}.png')))
                assert runtime.live_output.snapshot_frame().getchannel('A').getextrema() == (0, 255)
                page.locator('#clearLive').click()
                expect(page.locator('#liveStatus')).to_have_text('Transparent / Output running')
                assert runtime.live_output.snapshot_frame().getchannel('A').getextrema() == (0, 0)
                page.evaluate("switchTemplate('t11')")
                page.wait_for_function('previewReady')
                expect(page.locator('#takeLive')).to_be_enabled(timeout=15000)
                page.locator('#takeLive').click()
                expect(page.locator('#liveStatus')).to_have_text('On Air')
                page.wait_for_function('programReady && displayedProgramRevision === latestLive.program_revision')
                page.screenshot(path=str(Path(__file__).with_name(f'alpha-coming-next-{width}.png')))
                assert runtime.live_output.snapshot_frame().getchannel('A').getextrema() == (0, 255)
                page.locator('#liveButton').click()
                expect(page.locator('#liveStatus')).to_have_text('Output stopped')
                page.locator('#liveButton').click()
                page.locator('#clearMode').select_option('black')
                expect(page.locator('#keyerConfirmation')).not_to_be_visible()
                assert page.locator('#liveDevice option').count() == 4
                assert not scans, scans
                assert not errors, errors
                print(json.dumps({'viewport': width, 'fill_key_start_push_clear_stop': 'PASS', 'scan_requests': 0, 'browser_errors': errors}))
                page.close()
            browser.close()
    finally:
        runtime.stop_live(force=True)
        server.shutdown()
        server.server_close()
        thread.join()

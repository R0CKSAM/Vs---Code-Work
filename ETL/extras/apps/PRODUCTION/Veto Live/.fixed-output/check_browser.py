import json
from pathlib import Path
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(channel='chrome', headless=True)
    for width, height in [(1440, 1000), (390, 844)]:
        page = browser.new_page(viewport={'width': width, 'height': height})
        scans = []
        page.on('request', lambda request: scans.append(request.url)
                if '/api/output/capabilities' in request.url else None)
        page.goto('http://127.0.0.1:8080/scoreboard')
        page.wait_for_function("typeof boot !== 'undefined' && boot && !!document.querySelector('#editor').children.length")
        page.locator('#liveButton').click()
        assert page.locator('#liveDevice option').count() == 4
        assert page.locator('#livePreset').input_value() == 'HD 1080i50'
        for number in range(4):
            page.locator('#liveDevice').select_option(f'DeckLink output {number+1} (device {number})')
            assert page.locator('#livePreset').input_value() == 'HD 1080i50'
            assert page.locator('#startLive').is_disabled()
            page.locator('#receiverConfirmed').check()
            assert page.locator('#startLive').is_enabled()
        page.locator('#liveDevice').select_option('DeckLink output 1 (device 0)')
        page.screenshot(path=str(Path(__file__).with_name(f'fixed-output-{width}.png')))
        assert not scans, scans
        assert page.locator('#retryOutputCheck').count() == 0
        print(json.dumps({'viewport': width, 'fixed_devices': [0,1,2,3],
                          'default': 'HD 1080i50', 'scan_requests': len(scans)}))
        page.close()
    browser.close()

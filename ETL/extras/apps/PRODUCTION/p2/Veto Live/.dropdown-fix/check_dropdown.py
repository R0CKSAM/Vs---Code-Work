import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent
with sync_playwright() as p:
    browser = p.chromium.launch(channel='chrome', headless=True)
    for width, height in [(1440, 1000), (390, 844)]:
        page = browser.new_page(viewport={'width': width, 'height': height})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.route('**/scoreboard', lambda route: route.fulfill(
            content_type='text/html', body=(ROOT / 'scoreboard_web.html').read_text(encoding='utf-8')))
        page.route('**/api/output/capabilities', lambda route: route.fulfill(json={
            'devices': [], 'error': 'Test: driver unavailable'}))
        page.goto('http://127.0.0.1:8080/scoreboard')
        page.wait_for_function("typeof boot !== 'undefined' && boot && !!document.querySelector('#editor').children.length")
        page.locator('#liveButton').click()
        page.wait_for_function("document.querySelector('#liveDevice').textContent === 'Hardware check failed'")
        assert page.locator('#startLive').is_disabled()
        assert page.locator('#receiverConfirmed').is_disabled()
        page.unroute('**/api/output/capabilities')
        page.route('**/api/output/capabilities', lambda route: route.fulfill(json={'devices': [
            {'number': 0, 'name': 'DeckLink output 1 (device 0)', 'model': 'Test DeckLink',
             'modes': ['HD 1080i50', 'HD 1080p25']},
            {'number': 1, 'name': 'DeckLink output 2 (device 1)', 'model': 'Test DeckLink',
             'modes': ['HD 720p50']}
        ]}))
        page.locator('#retryOutputCheck').click()
        page.wait_for_function("document.querySelector('#liveDevice').options.length === 2")
        assert page.locator('#livePreset option').count() == 2
        page.locator('#liveDevice').select_option('DeckLink output 2 (device 1)')
        assert page.locator('#livePreset').input_value() == 'HD 720p50'
        page.locator('#receiverConfirmed').check()
        assert page.locator('#startLive').is_enabled()
        page.locator('#liveDevice').select_option('DeckLink output 1 (device 0)')
        assert page.locator('#startLive').is_disabled()
        page.locator('#livePreset').select_option('HD 1080p25')
        page.screenshot(path=str(ROOT / f'dropdown-{width}.png'))
        assert not errors, errors
        print(json.dumps({'viewport': width, 'options_visible_and_selectable': True, 'errors': errors}))
        page.close()
    browser.close()

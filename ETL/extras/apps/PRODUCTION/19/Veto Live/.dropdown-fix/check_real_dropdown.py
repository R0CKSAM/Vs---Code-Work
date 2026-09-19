import json
from pathlib import Path
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(channel='chrome', headless=True)
    for width, height in [(1440, 1000), (390, 844)]:
        page = browser.new_page(viewport={'width': width, 'height': height})
        page.goto('http://127.0.0.1:8080/scoreboard')
        page.wait_for_function("typeof boot !== 'undefined' && boot && !!document.querySelector('#editor').children.length")
        page.locator('#liveButton').click()
        page.wait_for_function("!document.querySelector('#liveDevice').disabled", timeout=20000)
        assert page.locator('#liveDevice option').count() == 4
        assert page.locator('#livePreset').input_value() == 'HD 1080i50'
        assert page.locator('#livePreset option').count() == 14
        assert page.locator('#startLive').is_disabled()
        page.screenshot(path=str(Path(__file__).with_name(f'real-dropdown-{width}.png')))
        print(json.dumps({'width': width, 'outputs': 4, 'selected_format': 'HD 1080i50',
                          'formats': 14, 'output_started': False}))
        page.close()
    browser.close()

"""Smoke-test platform/channel multi-select on the generated dashboard."""

from pathlib import Path

from playwright.sync_api import sync_playwright


HTML = Path(__file__).resolve().parents[1] / 'output' / 'watch_hours' / 'concurrency' / 'veto_concurrency.html'


def test_multiselect_filters():
    assert HTML.exists(), f'Generate dashboard first: {HTML}'
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 900})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(HTML.as_uri(), wait_until='domcontentloaded', timeout=120000)
        page.wait_for_function("document.querySelectorAll('#platformOptions input').length >= 2", timeout=120000)
        page.locator('#platformFilter summary').click()
        platform_inputs = page.locator('#platformOptions input')
        platform_inputs.nth(0).check()
        page.wait_for_function('selectedPlatforms.length === 1 && !document.body.classList.contains("rendering")', timeout=120000)
        assert page.locator('#platformFilter').evaluate('(node) => node.open')
        platform_inputs.nth(1).check()
        page.wait_for_function('selectedPlatforms.length === 2 && !document.body.classList.contains("rendering")', timeout=120000)
        assert page.locator('#platformFilter').evaluate('(node) => node.open')
        assert page.locator('#platformSummary').inner_text() == '2 platforms'
        assert page.evaluate('filteredRows().every(rowInPlatform)')

        page.locator('#channelFilter summary').click()
        assert not page.locator('#platformFilter').evaluate('(node) => node.open')
        channel_inputs = page.locator('#channelOptions input')
        assert channel_inputs.count() >= 2
        channel_inputs.nth(0).check()
        page.wait_for_function('selectedChannels.length === 1 && !document.body.classList.contains("rendering")', timeout=120000)
        assert page.locator('#channelFilter').evaluate('(node) => node.open')
        channel_inputs.nth(1).check()
        page.wait_for_function('selectedChannels.length === 2 && !document.body.classList.contains("rendering")', timeout=120000)
        assert page.locator('#channelFilter').evaluate('(node) => node.open')
        assert page.locator('#channelSummary').inner_text() == '2 channels'
        assert page.evaluate('filteredRows().length > 0')
        assert page.evaluate('filteredRows().every(row => rowInPlatform(row) && rowInChannel(row))')
        assert page.evaluate('filteredSummary().every(row => rowInPlatform(row) && rowInChannel(row))')
        page.locator('#title').click()
        assert not page.locator('#channelFilter').evaluate('(node) => node.open')
        page.locator('#channelFilter summary').click()
        page.keyboard.press('Escape')
        assert not page.locator('#channelFilter').evaluate('(node) => node.open')
        assert not errors, errors[:3]
        page.set_viewport_size({'width': 390, 'height': 844})
        assert page.locator('#channelFilter summary').is_visible()
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 2')
        browser.close()


if __name__ == '__main__':
    test_multiselect_filters()
    print('Concurrency multi-select smoke test passed')

"""Check that multi-select menus stay open for choices and close on dismissal."""

from pathlib import Path

from playwright.sync_api import sync_playwright


OUTPUT = Path(__file__).resolve().parents[1] / "output"


def test_audience_ops_menus() -> None:
    html = OUTPUT / "audience_ops" / "veto_audience_operations.html"
    assert html.exists(), f"Generate dashboard first: {html}"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(html.as_uri(), wait_until="domcontentloaded", timeout=180000)
        page.wait_for_function(
            'document.querySelectorAll("#platformMenu input[data-value]").length >= 2',
            timeout=180000,
        )
        if page.locator("#opsUniqueIpDateToggle").is_enabled():
            page.locator("#opsUniqueIpDateToggle").click()
            page.locator("#opsUniqueIpDateMenu .date-multi-actions button").nth(1).click()
            assert page.locator("#opsUniqueIpDateMenu").evaluate("node => node.classList.contains('open')")
            page.locator("#opsUniqueIpDateMenu input[type='checkbox']").first.click()
            assert page.locator("#opsUniqueIpDateMenu").evaluate("node => node.classList.contains('open')")
            page.mouse.click(4, 4)
            assert not page.locator("#opsUniqueIpDateMenu").evaluate("node => node.classList.contains('open')")
        page.locator("#platformToggle").click()
        for index in range(2):
            page.locator("#platformMenu input[data-value]").nth(index).click()
            assert page.locator("#platformMenu").evaluate("node => node.classList.contains('open')")
        page.locator("#channelToggle").click()
        assert not page.locator("#platformMenu").evaluate("node => node.classList.contains('open')")
        page.locator("#channelMenu input[data-value]").first.click()
        assert page.locator("#channelMenu").evaluate("node => node.classList.contains('open')")
        page.mouse.click(4, 4)
        assert not page.locator("#channelMenu").evaluate("node => node.classList.contains('open')")
        page.locator("#channelToggle").click()
        page.keyboard.press("Escape")
        assert not page.locator("#channelMenu").evaluate("node => node.classList.contains('open')")
        assert not errors, errors[:3]
        browser.close()


def test_master_menus() -> None:
    html = OUTPUT / "master" / "veto_master_dashboard.html"
    assert html.exists(), f"Generate dashboard first: {html}"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(html.as_uri(), wait_until="domcontentloaded", timeout=120000)
        page.wait_for_function(
            'document.querySelectorAll("#channelOptions input").length >= 2',
            timeout=120000,
        )
        page.locator("#channelSummary").click()
        for index in range(2):
            page.locator("#channelOptions input").nth(index).click()
            assert page.locator("#channelDetails").evaluate("node => node.open")
        page.locator("#geoCountrySummary").click()
        assert not page.locator("#channelDetails").evaluate("node => node.open")
        assert page.locator("#geoCountryDetails").evaluate("node => node.open")
        page.locator("#geoCountryOptions input").first.click()
        assert page.locator("#geoCountryDetails").evaluate("node => node.open")
        page.mouse.click(4, 4)
        assert not page.locator("#geoCountryDetails").evaluate("node => node.open")
        page.locator("#channelSummary").click()
        page.keyboard.press("Escape")
        assert not page.locator("#channelDetails").evaluate("node => node.open")
        assert not errors, errors[:3]
        browser.close()


def test_vod_menus() -> None:
    html = OUTPUT / "exports" / "vod_stream_query_analysis_dashboard.html"
    assert html.exists(), f"Generate dashboard first: {html}"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(html.as_uri(), wait_until="domcontentloaded", timeout=120000)
        page.wait_for_function(
            'document.querySelectorAll("#titleOptions input").length >= 2',
            timeout=120000,
        )
        page.locator("#titleToggle").click()
        for index in range(2):
            page.locator("#titleOptions input").nth(index).click()
            assert page.locator("#titlePicker").evaluate("node => node.classList.contains('open')")
        page.mouse.click(4, 4)
        assert not page.locator("#titlePicker").evaluate("node => node.classList.contains('open')")
        page.locator("#titleToggle").click()
        page.keyboard.press("Escape")
        assert not page.locator("#titlePicker").evaluate("node => node.classList.contains('open')")
        browser.close()


if __name__ == "__main__":
    test_audience_ops_menus()
    test_master_menus()
    test_vod_menus()
    print("Dashboard multi-select menu smoke tests passed")

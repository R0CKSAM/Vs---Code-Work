"""Optional real-browser smoke test for the served dashboard.

Run while the application is available on port 8000:
    python tests/browser_sanity.py
"""
from playwright.sync_api import sync_playwright


def main() -> None:
    console_errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on(
            "console",
            lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
        )
        page.route(
            "**/api/auth/me",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=(
                    '{"authenticated":true,"user":{"id":1,'
                    '"email":"sanity@example.com","full_name":"Sanity User",'
                    '"role":"USER","status":"APPROVED","permissions":[]}}'
                ),
            ),
        )
        response = page.goto("http://127.0.0.1:8000/", wait_until="networkidle")
        assert response and response.ok, "Dashboard did not load successfully"
        page.wait_for_selector("text=Overview")
        assert page.locator(".kpi-card").count() == 4
        assert page.locator(".website-card").count() == 7
        assert page.locator(".news-card").count() > 0

        page.locator('[data-route="news"]').click()
        page.wait_for_selector("text=News Intelligence Monitoring")
        published_cells = page.locator("tbody tr td:first-child").all_inner_texts()
        assert published_cells, "News table did not render publication times"
        assert not any(value.strip().startswith("~") for value in published_cells), (
            "A scrape timestamp was displayed as a publication timestamp"
        )

        page.locator('[data-route="advertisements"]').click()
        page.wait_for_selector("text=Verified advertisements")
        page.wait_for_selector("text=YouTube")
        ad_table_text = page.locator("#ads-table-container").inner_text()
        assert "Not identified" not in ad_table_text
        assert "Unknown placement" not in ad_table_text

        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(250)
        assert page.locator(".main-wrapper").is_visible()
        assert page.locator(".sidebar").evaluate("el => el.offsetWidth") == 68
        assert not console_errors, f"Browser console errors: {console_errors}"
        browser.close()

    print("browser sanity: PASS (desktop + mobile, no console errors)")


if __name__ == "__main__":
    main()

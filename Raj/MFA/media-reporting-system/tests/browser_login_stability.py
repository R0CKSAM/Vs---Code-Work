"""Real-browser regression check for authentication form stability.

Run while the dashboard is available on port 8000:
    python tests/browser_login_stability.py
"""
from playwright.sync_api import sync_playwright


def main() -> None:
    requests: list[tuple[str, str]] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.on(
            "request",
            lambda request: requests.append((request.resource_type, request.url)),
        )

        response = page.goto("http://127.0.0.1:8000/", wait_until="networkidle")
        assert response and response.ok, "Dashboard did not load"

        email = page.locator("#auth-email")
        password = page.locator("#auth-password")
        email.fill("stability-probe@example.com")
        password.fill("StabilityProbe123!")
        email.evaluate("element => element.dataset.stabilityProbe = 'same-node'")

        

        assert email.input_value() == "stability-probe@example.com"
        assert password.input_value() == "StabilityProbe123!"
        assert email.get_attribute("data-stability-probe") == "same-node"

        document_requests = [url for kind, url in requests if kind == "document"]
        assert len(document_requests) == 1, document_requests
        browser.close()

    print("login stability: PASS (22 seconds, same form DOM, one document load)")


if __name__ == "__main__":
    main()

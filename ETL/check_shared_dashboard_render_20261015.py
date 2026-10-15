"""Smoke-test the exact local dashboard artifacts used by the NAS publisher."""
import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = Path(__file__).resolve().parent
AUDIT = BASE / "output/validation/shared_dashboard_render_20261015"
PAGES = [
    "overview/overview_dashboard.html",
    "watch_hours/concurrency/veto_concurrency.html",
    "latency/veto_latency.html",
    "audience_ops/veto_audience_operations.html",
    "master/veto_master_dashboard.html",
    "watch_hours/veto_watch_hours.html",
    "device_decode/ua_decode_dashboard_preview.html",
    "watch_hours/stream_showcase/stream_watch_hours_showcase.html",
]


def main():
    AUDIT.mkdir(parents=True, exist_ok=True)
    scratch = AUDIT / "browser_temp"
    scratch.mkdir(exist_ok=True)
    os.environ["TMP"] = os.environ["TEMP"] = str(scratch)
    results = []
    with sync_playwright() as p:
        executable = next((str(path) for path in [
            Path(p.chromium.executable_path),
            Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
            Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
        ] if path.exists()), None)
        if not executable:
            raise RuntimeError("No Chromium browser found")
        browser = p.chromium.launch(executable_path=executable, headless=True)
        try:
            for relative in PAGES:
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                path = BASE / "output" / relative
                result = {"path": str(path), "errors": errors}
                try:
                    page.goto(path.as_uri(), wait_until="load", timeout=180000)
                    page.wait_for_timeout(2000)
                    result.update(page.evaluate("""() => ({title:document.title,
                        bodyTextLength:document.body.innerText.length,
                        canvasCount:document.querySelectorAll('canvas').length,
                        horizontalOverflow:document.documentElement.scrollWidth > innerWidth + 2})"""))
                    result["rendered"] = bool(result["title"] and result["bodyTextLength"] > 100)
                    if path.name in ("overview_dashboard.html", "veto_watch_hours.html"):
                        page.screenshot(path=str(AUDIT / (path.stem + ".png")))
                except Exception as exc:
                    result["rendered"] = False
                    result["failure"] = str(exc)
                finally:
                    page.close()
                results.append(result)
                (AUDIT / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
                print(json.dumps(result), flush=True)
        finally:
            browser.close()
    if any(not item["rendered"] or item["errors"] for item in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

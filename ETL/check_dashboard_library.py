"""Render packaged dashboards and exercise ASRUN's dynamically loaded sources."""
import json
import argparse
import os
from pathlib import Path

from playwright.sync_api import sync_playwright
from publish_dashboard_library import AUDIT, PACKAGE, SHARE


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only")
    parser.add_argument("--shared", action="store_true", help="Verify the published NAS copy")
    args = parser.parse_args()
    scratch = AUDIT / "browser_temp"
    scratch.mkdir(parents=True, exist_ok=True)
    os.environ["TMP"] = os.environ["TEMP"] = str(scratch)
    manifest = json.loads((AUDIT / "manifest.json").read_text(encoding="utf-8"))
    result_path = AUDIT / ("shared_browser_results.json" if args.shared else "browser_results.json")
    previous = json.loads(result_path.read_text(encoding="utf-8")) if args.only and result_path.exists() else []
    results = [item for item in previous if item["file"] != args.only]
    with sync_playwright() as p:
        executable = next(str(path) for path in (
            Path(p.chromium.executable_path),
            Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
            Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
        ) if path.exists())
        browser = p.chromium.launch(executable_path=executable, headless=True)
        try:
            for item in manifest:
                if args.only and item["file"] != args.only:
                    continue
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                errors, failed = [], []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("requestfailed", lambda request: failed.append({"url": request.url, "reason": request.failure}))
                result = {"file": item["file"], "errors": errors, "failed_requests": failed}
                try:
                    page.goto(((SHARE if args.shared else PACKAGE) / item["file"]).as_uri(), wait_until="load", timeout=180000)
                    page.wait_for_timeout(1500)
                    result.update(page.evaluate("""() => ({title:document.title,
                      textLength:document.body.innerText.length,
                      canvasCount:document.querySelectorAll('canvas').length,
                      brokenImages:[...document.images].filter(i=>i.src && (!i.complete || !i.naturalWidth)).length,
                      overflow:document.documentElement.scrollWidth > innerWidth+2})"""))
                    if item["file"] == "asrun_delivery_demo.html":
                        result["lazy_sources"] = page.evaluate("""async () => {
                          const result={};
                          for(const name of Object.keys(DATA.sidecars||{})) {
                            const c=DATA.sidecars[name];
                            const dates=Object.keys(c.dates||{}).sort();
                            if(c.partitioned && dates.length) {
                              await loadDashboardPartition(name,dates[dates.length-1]);
                            } else { await loadDashboardSource(name); }
                            result[name]=dates.length ? dates[dates.length-1] : 'loaded';
                          }
                          const nct=await loadNctManifest();
                          const date=Object.keys(nct.dates||{}).sort().pop();
                          if(date) { await loadNctPartition(date,nct.dates[date]); result.nct=date; }
                          return result;
                        }""")
                    result["rendered"] = result["textLength"] > 60
                    if item["file"] in ("asrun_delivery_demo.html", "stream_watch_hours_showcase.html", "CTV_FCT_Dashboard.html"):
                        page.screenshot(path=str(AUDIT / (Path(item["file"]).stem + ".png")))
                except Exception as exc:
                    result["rendered"] = False
                    result["failure"] = str(exc)
                finally:
                    page.close()
                results.append(result)
                result_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
                print(json.dumps(result), flush=True)
        finally:
            browser.close()
    if any(not r["rendered"] or r["errors"] or any(f["url"].startswith("file:") for f in r["failed_requests"]) for r in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

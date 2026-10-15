"""Package current standalone dashboards without modifying their source artifacts."""
from __future__ import annotations

import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
from datetime import datetime
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
AUDIT = ROOT / "ETL/output/validation/dashboard_library_20261015"
SHARE = Path("Z:/Veto Logs Backup/Dashboards")
PACKAGE = AUDIT / "package"

# Latest usable export per dashboard, not source templates or superseded builds.
REPORTS = [
    ("overview_dashboard.html", "ETL/output/overview/overview_dashboard.html", "Core ETL through 2026-10-14"),
    ("veto_concurrency.html", "ETL/output/watch_hours/concurrency/veto_concurrency.html", "Core ETL through 2026-10-14"),
    ("veto_latency.html", "ETL/output/latency/veto_latency.html", "Core ETL through 2026-10-14"),
    ("veto_audience_operations.html", "ETL/output/audience_ops/veto_audience_operations.html", "Core ETL through 2026-10-14"),
    ("veto_master_dashboard.html", "ETL/output/master/veto_master_dashboard.html", "Core ETL through 2026-10-14"),
    ("veto_watch_hours.html", "ETL/output/watch_hours/veto_watch_hours.html", "Core ETL through 2026-10-14"),
    ("ua_decode_dashboard_preview.html", "ETL/output/device_decode/ua_decode_dashboard_preview.html", "Latest saved decode preview; generated 2026-10-14"),
    ("stream_watch_hours_showcase.html", "ETL/output/validation/dashboard_library_20261015/refreshed_showcase/stream_watch_hours_showcase.html", "Regenerated; 2026-08-01 through 2026-10-14"),
    ("asrun_delivery_demo.html", "ETL/asrun_demo/output/asrun_delivery_demo.html", "Generated 2026-10-15; ASRUN logs through Oct 11; other source coverage varies"),
    ("channel_average_graph_style_options.html", "ETL/output/watch_hours/channel_average_graph_style_options.html", "Saved chart style comparison"),
    ("vod_stream_query_analysis_dashboard.html", "ETL/output/exports/vod_stream_query_analysis_dashboard.html", "Latest saved export; generated 2026-10-05"),
    ("viewer_journey_menu.html", "ETL/output/exports/viewer_journey/viewer_journey_menu.html", "Historical viewer journey export"),
    ("veto_audience_cdn_war_room_2026-09-02.html", "ETL/output/exports/veto_audience_cdn_war_room_2026-09-02.html", "Historical 2026-09-02 report"),
    ("watch_hours_phase1.html", "ETL/class/watch_hours_phase1.html", "Historical phase-one report; latest saved version"),
    ("veto_cdn_analysis.html", "ETL/asrun_demo/veto_cdn_analysis.html", "Saved CDN analysis"),
    ("channel_distribution_dashboard.html", "reverseEngg/channel_distribution_dashboard_shared.html", "Historical distribution export"),
    ("chrome_report_dashboard.html", "reverseEngg/chrome_report_dashboard (1).html", "Historical Chrome distribution export"),
    ("CTV_FCT_Dashboard.html", "reverseEngg/CTV DASHBOARD/CTV_FCT_Dashboard_updated.html", "Historical CTV FCT; latest updated export"),
    ("channel_distribution_detail.html", "r-j/P4 - Distribution details/dashboard/dashboard_output.html", "Historical distribution detail export"),
    ("vglive_stakeholder_report.html", "ETL/extras/old_html_reports/vglive_stakeholder_report.html", "Historical stakeholder report"),
    ("user_agent_analysis_report.html", "ETL/extras/old_html_reports/Reports_1.UA_UA.html", "Historical user-agent report"),
    ("vglive_live_tv_dashboard.html", "ETL/extras/old_html_reports/file_VgLiveDashboard.html", "Historical Live TV dashboard"),
    ("speednews_drop_analysis.html", "ETL/extras/apps/speednews_drop_analysis.html", "Historical Speednews report"),
]


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def safe_path(root, relative):
    target = (root / relative).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError(f"Path outside package scope: {relative}")
    return target


def shared_source(source):
    """Keep historical inputs usable after the shared-folder tidy-up."""
    if not source.exists() and source.is_relative_to(SHARE):
        relative = source.relative_to(SHARE)
        if relative.parts[0] in ("identity_poc", "PEAK", "CTV - Distribution"):
            return safe_path(SHARE / "extras", relative)
    return source


def stable_copy(source, target):
    before = source.stat()
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    after = source.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError(f"Source changed during publication: {source}")
    if digest(source) != digest(target):
        raise RuntimeError(f"Copy verification failed: {source}")


class References(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs = []
        self.has_base = False

    def handle_starttag(self, tag, attrs):
        self.has_base |= tag == "base"
        for key, value in attrs:
            if key in ("src", "href") and value:
                self.refs.append((tag, key, value))


def js_data(path):
    text = path.read_text(encoding="utf-8-sig")
    return json.JSONDecoder().raw_decode(text.split("=", 1)[1].lstrip())[0]


def manifest_files(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from manifest_files(item)
    elif isinstance(value, list):
        for item in value:
            yield from manifest_files(item)
    elif isinstance(value, str):
        parsed = urlsplit(value)
        if not parsed.scheme and parsed.path.endswith((".js", ".csv", ".json")):
            yield unquote(parsed.path)


def package_one(name, source, note):
    content = source.read_text(encoding="utf-8-sig")
    refs = References()
    refs.feed(content)
    dep = PACKAGE / "dependency" / Path(name).stem
    assets = set()
    external = []
    for tag, key, value in refs.refs:
        parsed = urlsplit(value)
        if value.startswith(("#", "data:", "javascript:", "mailto:")):
            continue
        if parsed.scheme or parsed.netloc:
            external.append(value)
            continue
        if parsed.path:
            assets.add(unquote(parsed.path))
    if name == "asrun_delivery_demo.html":
        data = js_data(source.parent / "asrun_delivery_data.js")
        assets.update(manifest_files(data.get("sidecars", {})))
        assets.update(manifest_files(data.get("nct", {})))
        assets.add("nct_story_data.js")
        assets.update(manifest_files(js_data(source.parent / "nct_story_data.js")))
        assets.add("asrun_ad_events.csv")
    if name == "vod_stream_query_analysis_dashboard.html":
        decoder = json.JSONDecoder()
        index = decoder.raw_decode(content.split("const dashboardIndex=", 1)[1].lstrip())[0]
        directory = decoder.raw_decode(content.split("const dataDirectory=", 1)[1].lstrip())[0]
        assets.update(f"{directory}/{date}.js" for date in index["dates"])
    for asset in sorted(assets):
        stable_copy(safe_path(source.parent, asset), safe_path(dep, asset))
    # A base URL also covers dynamically-created script tags in ASRUN's lazy tabs.
    if assets:
        if refs.has_base:
            raise RuntimeError(f"Existing base URL requires explicit handling: {name}")
        base = f'./dependency/{Path(name).stem}/'
        match = re.search(r"<head\b[^>]*>", content, re.I)
        if not match:
            raise RuntimeError(f"No head for dependency base: {name}")
        content = content[:match.end()] + f'<base href="{base}">' + content[match.end():]
    target = PACKAGE / name
    if assets:
        target.write_text(content, encoding="utf-8")
    else:
        stable_copy(source, target)
    return {"file": name, "source": str(source), "note": note,
            "source_modified": datetime.fromtimestamp(source.stat().st_mtime).isoformat(),
            "source_sha256": digest(source), "sha256": digest(target),
            "dependencies": sorted(assets), "external_urls": sorted(set(external))}


def build(only=None):
    PACKAGE.mkdir(parents=True, exist_ok=True)
    reports = [(name, ROOT / path, note) for name, path, note in REPORTS]
    journeys = list((ROOT / "ETL/output/exports/cliip_journey").glob("*/cliip_journey_dashboard.html"))
    if journeys:
        reports.append(("cliip_journey_dashboard.html", max(journeys, key=lambda p: p.stat().st_mtime), "Historical individual viewer journey"))
    reports.append(("identity_resolution_demo_2026-07-05.html", shared_source(SHARE / "identity_poc/identity_resolution_demo_2026-07-05.html"), "Historical identity resolution proof of concept"))
    peak = shared_source(SHARE / "PEAK/stream_watch_hours_showcase.html")
    if peak.exists():
        reports.append(("stream_watch_hours_peak_snapshot.html", peak, "Historical PEAK snapshot, preserved separately"))
    previous = json.loads((AUDIT / "manifest.json").read_text(encoding="utf-8")) if only else []
    results = [item for item in previous if item["file"] != only]
    for name, source, note in reports:
        if only and name != only:
            continue
        item = package_one(name, source, note)
        results.append(item)
        print(json.dumps({"packaged": name, "dependencies": len(item["dependencies"])}), flush=True)
    (AUDIT / "manifest.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    lines = ["VETO SHARED DASHBOARD LIBRARY", f"Packaged {datetime.now().isoformat(timespec='seconds')}",
             "", "Open HTML files in this folder. Keep the dependency folder beside them.",
             "These are copies, not a live sync. Run the publisher again after newer builds.",
             "Core ETL and refreshed STREAM Showcase cover 14 October 2026.",
             "Historical reports retain their original dates. Generated date is not data coverage.",
             "Some historical pages use optional internet-hosted fonts; fallback fonts work offline.", ""]
    for item in results:
        lines.append(f"{item['file']} | {item['note']}")
    lines += ["", "SERVER-BACKED APPS (not standalone file exports)",
              "RevenueLive: https://vetoanalytics.in (requires login and running server/database).",
              "Live Monitor, Live Concurrency, recorder and production scoreboard require their running services.",
              "Their frontend source files are not copied as non-working standalone dashboards.",
              "Source templates, smoke tests, duplicate older builds and graphics generators are excluded.",
              "Historical originals and older supporting exports are retained in extras; no data or code was deleted.",
              "Keep extras for historical source exports and future rebuilds; it is not an automatically disposable cache."]
    (PACKAGE / "README-CURRENT-DASHBOARDS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def publish():
    manifest = json.loads((AUDIT / "manifest.json").read_text(encoding="utf-8"))
    checks = json.loads((AUDIT / "browser_results.json").read_text(encoding="utf-8"))
    if {r["file"] for r in checks} != {r["file"] for r in manifest}:
        raise RuntimeError("Browser checks do not cover the complete library")
    if any(not r["rendered"] or r["errors"] or any(
        f["url"].startswith("file:") for f in r["failed_requests"]
    ) for r in checks):
        raise RuntimeError("Resolve browser errors before publication")
    # Fail before changing the share if any completed artifact changed after packaging.
    for item in manifest:
        if digest(shared_source(Path(item["source"]))) != item["source_sha256"]:
            raise RuntimeError(f"Source changed; rebuild package: {item['file']}")
    run = datetime.now().strftime("%Y%m%d_%H%M%S")
    records = []
    # Publish dependencies first; each individual file is swapped only after hash verification.
    files = sorted(PACKAGE.rglob("*"), key=lambda p: (p.suffix.lower() == ".html", str(p)))
    for source in files:
        if not source.is_file():
            continue
        rel = source.relative_to(PACKAGE)
        target = safe_path(SHARE, rel)
        expected = digest(source)
        if target.exists() and digest(target) == expected:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        stage = target.with_name(target.name + f".{run}.pending")
        stable_copy(source, stage)
        if target.exists():
            backup = safe_path(AUDIT / "previous_shared" / run, rel)
            stable_copy(target, backup)
        stage.replace(target)
        records.append({"path": str(rel), "bytes": source.stat().st_size, "sha256": expected})
        if source.suffix == ".html":
            print(f"Published {source.name}", flush=True)
    (AUDIT / f"publication_{run}.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    print(json.dumps({"updated_files": len(records), "html_dashboards": len(manifest), "destination": str(SHARE)}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "publish"))
    parser.add_argument("--only", help="Rebuild one dashboard without copying unchanged large exports")
    args = parser.parse_args()
    build(args.only) if args.action == "build" else publish()

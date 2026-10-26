"""Verify an accepted incident before recovery skips it; not a full-day checkpoint."""
import argparse
from datetime import date
import json
from pathlib import Path

from cleanup_daily_intermediates import load_validation_report, parquet_rows


def verify(path, day, root):
    receipt = json.loads(path.read_text())
    if (receipt.get("date") != day or receipt.get("status") != "processed_with_confirmed_source_gap"
            or receipt.get("full_day_complete") is not False or receipt.get("dashboard_eligible") is not False):
        raise ValueError("Invalid CDN closeout")
    evidence = {}
    for key in ("approval", "validation_report", "cleanup_manifest"):
        target = Path(receipt[key]).resolve(strict=True)
        if not target.is_relative_to((root / "output").resolve()):
            raise ValueError("Incident evidence escaped output directory")
        evidence[key] = target
    load_validation_report(evidence["validation_report"], day, ["fast", "stream"],
                           allow_lake_only=True, coverage_exception=evidence["approval"])
    cleanup = json.loads(evidence["cleanup_manifest"].read_text())
    if cleanup.get("date") != day or cleanup.get("status") != "complete":
        raise ValueError("Incident cleanup incomplete")
    checks = cleanup.get("checks", [])
    if len(checks) != 2 or {c["source"] for c in checks} != {"fast", "stream"}:
        raise ValueError("Missing source reconciliation")
    for check in checks:
        if (check["evidence_rows"] <= 0 or check["evidence_rows"] != check["lake_rows"]
                or sum(parquet_rows(Path(p)) for p in check["lake_files"]) != check["lake_rows"]):
            raise ValueError("Retained incident lake no longer matches reconciliation")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--etl-root", type=Path, required=True)
    parser.add_argument("--date", type=date.fromisoformat, required=True)
    args = parser.parse_args()
    verify(args.etl_root / "output/state/cdn_incident_closeout" / f"{args.date}.json", str(args.date), args.etl_root)
    print(f"{args.date}: accepted source gap verified; not dashboard eligible")

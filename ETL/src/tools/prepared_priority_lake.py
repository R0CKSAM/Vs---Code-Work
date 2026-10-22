"""Adopt validated priority lake outputs for normal ETL without rebuilding raw data."""
import argparse
import json
import os
from pathlib import Path

from priority_stream_lake import ETL, atomic_json, pq, sha256


def fingerprint(path):
    path = path.resolve()
    stat = path.stat()
    return dict(path=str(path), bytes=stat.st_size, mtime_ns=stat.st_mtime_ns)


def link_verified(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if not os.path.samefile(source, target) and sha256(source) != sha256(target):
            raise RuntimeError(f"Refusing conflicting prepared output: {target}")
    else:
        os.link(source, target)


def verify(receipt, base):
    data = json.loads(receipt.read_text(encoding="utf-8"))
    if data.get("status") not in {"prepared", "lake_ready"} or set(data["sources"]) != {"fast", "stream"}:
        raise RuntimeError("Invalid prepared-lake receipt")
    for source, item in data["sources"].items():
        checkpoint = ETL / "output/state/downloads" / f"{data['date']}_{source}.json"
        if sha256(checkpoint) != item["download_checkpoint_sha256"]:
            raise RuntimeError("Download checkpoint changed; prepared lake must be reviewed")
        lake_only = data["status"] == "lake_ready"
        for record in ([item["final"]] if not lake_only else []) + item["lake"]:
            path = Path(record["path"]).resolve()
            if not path.is_relative_to(base.resolve()) or fingerprint(path) != record:
                raise RuntimeError(f"Prepared output changed or escaped data root: {path}")
        rows = int(item["rows"]) if lake_only else pq.read_metadata(item["final"]["path"]).num_rows
        if rows <= 0 or rows != sum(pq.read_metadata(p["path"]).num_rows for p in item["lake"]):
            raise RuntimeError("Prepared final/lake row count mismatch")
    return data


def adopt(work_roots, base):
    for root, state_name in ((work_roots["fast"], "asrun_state.json"),
                             (work_roots["stream"], "priority_state.json")):
        if json.loads((root / state_name).read_text())["status"] != "complete":
            raise RuntimeError("Priority work is not complete")
    for day in ("2026-10-10", "2026-10-11"):
        receipt = dict(status="prepared", date=day, sources={})
        year, month, day_number = day.split("-")
        for source, work in work_roots.items():
            run = work / day
            source_id = f"{source}_{day.replace('-', '_')}"
            final = run / f"{source_id}_final_clean.parquet"
            lake = run / "lake"
            parts = sorted(lake.glob(f"source={source}/year=*/month=*/day=*/part_{source_id}_*.parquet"))
            if pq.read_metadata(final).num_rows != sum(pq.read_metadata(p).num_rows for p in parts):
                raise RuntimeError("Priority row counts no longer reconcile")
            final_target = base / f"stage/final_clean/source={source}/year={year}/month={month}/day={day_number}" / final.name
            link_verified(final, final_target)
            records = []
            for part in parts:
                target = base / "lake" / part.relative_to(lake)
                link_verified(part, target)
                records.append(fingerprint(target))
            checkpoint = ETL / "output/state/downloads" / f"{day}_{source}.json"
            receipt["sources"][source] = dict(final=fingerprint(final_target), lake=records,
                                              download_checkpoint_sha256=sha256(checkpoint))
        path = ETL / "output/state/prepared_lake" / f"{day}.json"
        atomic_json(path, receipt)
        verify(path, base)
        print(f"Prepared {day}: verified FAST/STREAM outputs linked into normal data root", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--fast-work", type=Path)
    parser.add_argument("--stream-work", type=Path)
    args = parser.parse_args()
    if args.verify:
        verify(args.verify, args.base)
        print("Prepared lake verified; only raw conversion/dedupe/partitioning may be skipped")
    else:
        adopt(dict(fast=args.fast_work, stream=args.stream_work), args.base)


if __name__ == "__main__":
    main()

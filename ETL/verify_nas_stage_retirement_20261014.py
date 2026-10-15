"""Read-only verification of four completed, relocated priority stage batches."""
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq

BASE = Path(__file__).resolve().parent
ARCHIVE = Path(r"\\192.168.50.11\analysis team\Veto Logs Backup\DO NOT DELETE")
RETAINED = ARCHIVE / "Temp/VetoETL/retained_intermediates"
AUDIT = BASE / "output/validation/nas_stage_retirement_20261014"


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def fingerprint(path):
    stat = path.stat()
    return {"bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def digest(path):
    before = fingerprint(path)
    h = hashlib.sha256()
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_SEQUENTIAL", 0)
    with os.fdopen(os.open(path, flags), "rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            h.update(block)
    require(before == fingerprint(path), f"File changed: {path}")
    return h.hexdigest()


def scoped(path, root):
    require(path.is_relative_to(root), f"Out of scope: {path}")
    for ancestor in (path, *path.parents):
        require(not ancestor.is_symlink() and not ancestor.is_junction(), f"Link: {ancestor}")
        if ancestor == root:
            break


def main():
    require(read(BASE / "output/temp/backlog_repair_20261014/state.json")["phase"] == "complete", "Recovery incomplete")
    relocated = read(BASE / "output/temp/priority_stage_relocation_20261012.json")
    require(relocated["status"] == "complete", "Relocation incomplete")
    provenance = {f["destination"].lower(): f for f in relocated["files"]}
    report = {"status": "verifying", "created_at_utc": datetime.now(timezone.utc).isoformat(),
              "groups": [], "files": [], "lake_files": [], "preserved": ["legacy_stream_20261011_parquet", "cleanup_20261014"]}
    AUDIT.mkdir(parents=True, exist_ok=True)
    for source, run, receipt in [
        ("fast", "asrun_priority_20261012_1700", "fast_archive_state.json"),
        ("stream", "stream_lake_priority_20261012_1600", "priority_state.json"),
    ]:
        prior = read(BASE / "output/temp" / run / receipt)
        require(prior["status"] == "complete", "Archive receipt incomplete")
        hashes = {f["destination"].lower(): f["verification"]["sha256"] for f in prior["files"]}
        for day in ("2026-10-10", "2026-10-11"):
            print(f"VERIFY {source} {day}", flush=True)
            key = f"{source}_{day.replace('-', '_')}"
            local = BASE / "output/temp" / run / day
            etl2 = read(local / ".etl_02_state.json")[key]
            etl3 = read(local / ".etl_03_state.json")[key + "_final_clean.parquet"]
            retired = read(BASE / f"output/validation/stage_retirement_20261014/{day}.json")
            require(retired["status"] == "complete", "Stage retirement incomplete")
            check = next(c for c in retired["checks"] if c["source"] == source)
            require(etl2["status"] == etl3["status"] == "ok", "ETL stage failed")
            require(etl2["rows"] == etl3["rows"] == check["rows"], "Output counts disagree")
            require(len(check["lake_files"]) == etl3["promoted_files"], "Missing lake partition")
            lake_rows = 0
            for name in check["lake_files"]:
                path = Path(name)
                scoped(path, ARCHIVE / f"source={source}")
                meta = pq.ParquetFile(path).metadata
                lake_rows += meta.num_rows
                info = {"path": str(path), **fingerprint(path), "rows": meta.num_rows}
                expected = hashes.get(str(path).lower())
                if expected:
                    info["expected_sha256"] = expected
                    require(info["bytes"] == next(f["verification"]["metadata"]["bytes"] for f in prior["files"] if f["destination"].lower() == str(path).lower()), "Archive size mismatch")
                report["lake_files"].append(info)
            require(lake_rows == etl3["rows"], "Lake row reconciliation failed")
            folder = RETAINED / run / day / "parquet"
            scoped(folder, RETAINED)
            files = sorted(folder.iterdir())
            expected_files = {name for name in provenance if str(Path(name).parent).lower() == str(folder).lower()}
            require({str(p).lower() for p in files} == expected_files and files, "Relocated file inventory differs")
            input_rows = 0
            for index, path in enumerate(files, 1):
                scoped(path, folder)
                require(path.is_file() and path.suffix == ".parquet", "Unexpected stage entry")
                old = provenance[str(path).lower()]
                info = {"path": str(path), "root": str(folder), **fingerprint(path)}
                require(info["bytes"] == old["bytes"], "Relocated size changed")
                info["expected_sha256"] = old["sha256"]
                info["rows"] = pq.ParquetFile(path).metadata.num_rows
                input_rows += info["rows"]
                report["files"].append(info)
                if index % 10 == 0:
                    print(f"  Stage metadata {index}/{len(files)}", flush=True)
            require(input_rows == etl2["input_rows"], "ETL input row reconciliation failed")
            report["groups"].append({"source": source, "date": day, "input_rows": input_rows,
                                     "deduplicated_lake_rows": lake_rows, "files": len(files)})
    require(len(report["files"]) == 225, "Unexpected overall file count")
    items = report["files"] + [f for f in report["lake_files"] if "expected_sha256" in f]
    print(f"Fresh checksum verification: {len(items)} files, 4 read workers", flush=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = {pool.submit(digest, Path(info["path"])): info for info in items}
        count = 0
        for future in as_completed(jobs):
            info = jobs[future]
            info["sha256"] = future.result()
            require(info["sha256"].lower() == info["expected_sha256"].lower(), f"Checksum mismatch: {info['path']}")
            require(fingerprint(Path(info["path"])) == {k: info[k] for k in ("bytes", "mtime_ns")}, "File changed since metadata check")
            count += 1
            if count % 10 == 0 or count > len(items) - 7:
                print(f"Checksums passed {count}/{len(items)}", flush=True)
    report["status"] = "verified"
    report["bytes"] = sum(f["bytes"] for f in report["files"])
    target = AUDIT / "verified_plan.json"
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"VERIFIED: {len(report['files'])} files, {report['bytes']} bytes. Plan: {target}", flush=True)


if __name__ == "__main__":
    main()

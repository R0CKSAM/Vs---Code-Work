"""Convert the October/11 Veto gzip JSONL folder to schema-complete Parquet.

This follows the conventions in 001.py, 02.py, and 03.py, but deliberately
discovers the schema across every source row before writing.  Consequently,
all output parts have the same schema and a column that appears late in the
input cannot be silently dropped.
"""

from __future__ import annotations

import csv
import gzip
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from tqdm import tqdm

try:
    import orjson
except ImportError:  # Keep the converter runnable on the current Python install.
    orjson = None
    import json


INPUT_DIR = Path(
    r"Z:\Vs - Code Work\ETL\data\raw\Veto Logs Backup\Veto Stream Backup\10\11"
)
OUTPUT_DIR = INPUT_DIR.parent / "11_parquet"

WORKERS = min(max(1, (os.cpu_count() or 4) - 1), 12)
BATCH_SIZE = 10_000
ROW_BUFFER = 100_000
ROW_GROUP_SIZE = 200_000
COMPRESSION = "zstd"
COMPRESSION_LEVEL = 3
PLACEHOLDERS = {"-", "^"}
# The owner confirmed that every gzip file has the same schema.  Sampling one
# complete file avoids a costly full-dataset schema pass.
ASSUME_IDENTICAL_SCHEMA = True


def json_loads(raw: bytes):
    if orjson is not None:
        return orjson.loads(raw)
    return json.loads(raw)


def compact_json(value) -> str:
    if orjson is not None:
        return orjson.dumps(value).decode("utf-8")
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def list_source_files() -> list[Path]:
    print(f"Scanning source file names: {INPUT_DIR}", flush=True)
    started = time.time()
    paths: list[Path] = []
    with os.scandir(INPUT_DIR) as entries:
        for entry in entries:
            if entry.is_file() and entry.name.lower().endswith(".gz"):
                paths.append(Path(entry.path))
                if len(paths) % 100_000 == 0:
                    print(f"  found {len(paths):,} files ...", flush=True)
    paths.sort(key=lambda path: path.name)
    print(
        f"Found {len(paths):,} .gz files in {(time.time() - started):.1f}s",
        flush=True,
    )
    return paths


def discover_complete_schema(paths: list[Path]) -> tuple[list[str], list[dict[str, str]]]:
    """Read every JSON object once and return every top-level key."""
    print("Discovering the complete schema across all source rows ...", flush=True)
    columns: set[str] = set()
    errors: list[dict[str, str]] = []
    bar = tqdm(paths, unit="file", desc="Schema scan", dynamic_ncols=True)

    for path in bar:
        try:
            with gzip.open(path, "rb") as source:
                for line_number, raw in enumerate(source, 1):
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        obj = json_loads(raw)
                        if isinstance(obj, dict):
                            columns.update(str(key) for key in obj)
                        else:
                            errors.append(
                                {
                                    "stage": "schema",
                                    "file": str(path),
                                    "line": str(line_number),
                                    "error": "JSON value is not an object",
                                }
                            )
                    except Exception as exc:
                        errors.append(
                            {
                                "stage": "schema",
                                "file": str(path),
                                "line": str(line_number),
                                "error": f"JSON: {exc}",
                            }
                        )
        except Exception as exc:
            errors.append(
                {
                    "stage": "schema",
                    "file": str(path),
                    "line": "",
                    "error": str(exc),
                }
            )

    result = sorted(columns)
    print(f"Complete schema: {len(result):,} columns", flush=True)
    print("Columns: " + ", ".join(result), flush=True)
    return result, errors


def convert_batch(task: dict) -> dict:
    output_path = Path(task["output_path"])
    temp_path = output_path.with_suffix(".parquet.tmp")
    columns: list[str] = task["columns"]
    schema = pa.schema([pa.field(column, pa.string()) for column in columns])
    buffer: list[dict] = []
    writer = None
    rows_written = 0
    files_ok = 0
    errors: list[dict[str, str]] = []

    def flush() -> None:
        nonlocal writer, rows_written
        if not buffer:
            return
        normalized = [{column: row.get(column) for column in columns} for row in buffer]
        table = pa.Table.from_pylist(normalized, schema=schema)
        if writer is None:
            writer = pq.ParquetWriter(
                temp_path,
                schema,
                compression=COMPRESSION,
                compression_level=COMPRESSION_LEVEL,
            )
        writer.write_table(table, row_group_size=ROW_GROUP_SIZE)
        rows_written += len(buffer)
        buffer.clear()

    try:
        for source_path_text in task["files"]:
            source_path = Path(source_path_text)
            file_had_read_error = False
            try:
                with gzip.open(source_path, "rb") as source:
                    for line_number, raw in enumerate(source, 1):
                        raw = raw.strip()
                        if not raw:
                            continue
                        try:
                            obj = json_loads(raw)
                            if not isinstance(obj, dict):
                                raise ValueError("JSON value is not an object")
                        except Exception as exc:
                            errors.append(
                                {
                                    "stage": "convert",
                                    "file": str(source_path),
                                    "line": str(line_number),
                                    "error": f"JSON: {exc}",
                                }
                            )
                            continue

                        row = {}
                        for key, value in obj.items():
                            key = str(key)
                            if value is None:
                                row[key] = None
                            elif isinstance(value, (dict, list)):
                                row[key] = compact_json(value)
                            else:
                                value_text = str(value)
                                row[key] = None if value_text in PLACEHOLDERS else value_text
                        buffer.append(row)
                        if len(buffer) >= ROW_BUFFER:
                            flush()
                files_ok += 1
            except Exception as exc:
                file_had_read_error = True
                errors.append(
                    {
                        "stage": "convert",
                        "file": str(source_path),
                        "line": "",
                        "error": str(exc),
                    }
                )
            if file_had_read_error:
                continue

        flush()
        if writer is None:
            # Retain the agreed schema even for a batch containing no valid rows.
            pq.write_table(
                pa.Table.from_pylist([], schema=schema),
                temp_path,
                compression=COMPRESSION,
                compression_level=COMPRESSION_LEVEL,
            )
        else:
            writer.close()
            writer = None
        temp_path.replace(output_path)
        return {
            "status": "ok",
            "part": output_path.name,
            "rows": rows_written,
            "files_ok": files_ok,
            "errors": errors,
        }
    except Exception as exc:
        if writer is not None:
            try:
                writer.close()
            except Exception:
                pass
        try:
            temp_path.unlink(missing_ok=True)
        except Exception:
            pass
        return {
            "status": "error",
            "part": output_path.name,
            "rows": rows_written,
            "files_ok": files_ok,
            "errors": errors,
            "fatal_error": str(exc),
        }


def matching_output_schema(path: Path, columns: list[str]) -> bool:
    try:
        return pq.read_schema(path).names == columns
    except Exception:
        return False


def write_errors(rows: list[dict[str, str]]) -> None:
    error_path = OUTPUT_DIR / "conversion_errors.csv"
    with error_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["timestamp", "stage", "file", "line", "error"],
        )
        writer.writeheader()
        timestamp = datetime.now(timezone.utc).isoformat()
        for row in rows:
            writer.writerow({"timestamp": timestamp, **row})


def main() -> None:
    if not INPUT_DIR.is_dir():
        raise SystemExit(f"Input folder not found: {INPUT_DIR}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    paths = list_source_files()
    if not paths:
        raise SystemExit("No .gz files found.")

    schema_paths = paths[:1] if ASSUME_IDENTICAL_SCHEMA else paths
    if ASSUME_IDENTICAL_SCHEMA:
        print("Identical source schema confirmed; inspecting the first gzip only.", flush=True)
    columns, all_errors = discover_complete_schema(schema_paths)
    if not columns:
        write_errors(all_errors)
        raise SystemExit("No JSON object columns were found.")

    tasks = []
    skipped = 0
    for part_number, start in enumerate(range(0, len(paths), BATCH_SIZE)):
        output_path = OUTPUT_DIR / f"part_{part_number:07d}.parquet"
        if output_path.exists() and matching_output_schema(output_path, columns):
            skipped += 1
            continue
        tasks.append(
            {
                "output_path": str(output_path),
                "files": [str(path) for path in paths[start : start + BATCH_SIZE]],
                "columns": columns,
            }
        )

    print(f"Output folder: {OUTPUT_DIR}", flush=True)
    print(f"Batches total: {(len(paths) + BATCH_SIZE - 1) // BATCH_SIZE:,}", flush=True)
    print(f"Batches already complete: {skipped:,}", flush=True)
    print(f"Batches to convert: {len(tasks):,}", flush=True)

    total_rows = 0
    fatal_batches = 0
    with ProcessPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(convert_batch, task): task for task in tasks}
        bar = tqdm(total=len(futures), unit="batch", desc="Converting", dynamic_ncols=True)
        for future in as_completed(futures):
            try:
                result = future.result()
            except Exception as exc:
                task = futures[future]
                result = {
                    "status": "error",
                    "part": Path(task["output_path"]).name,
                    "rows": 0,
                    "errors": [],
                    "fatal_error": str(exc),
                }
            total_rows += result.get("rows", 0)
            all_errors.extend(result.get("errors", []))
            if result["status"] != "ok":
                fatal_batches += 1
                all_errors.append(
                    {
                        "stage": "batch",
                        "file": result.get("part", ""),
                        "line": "",
                        "error": result.get("fatal_error", "unknown batch failure"),
                    }
                )
            bar.set_postfix(rows=f"{total_rows:,}", errors=len(all_errors))
            bar.update(1)
        bar.close()

    write_errors(all_errors)
    print("Conversion finished.", flush=True)
    print(f"Rows written this run: {total_rows:,}", flush=True)
    print(f"Errors: {len(all_errors):,}", flush=True)
    print(f"Fatal batches: {fatal_batches:,}", flush=True)
    print(f"Parquet output: {OUTPUT_DIR}", flush=True)

    if fatal_batches:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

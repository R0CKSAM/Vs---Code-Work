SPORTS AUDIENCE STORE

data/<IST date>/*.parquet is the appendable dataset. Each file has the requested 12 columns.
Partition identity is date plus workbook host. Existing completed partitions are never replaced.
Actual ReqHost values are preserved. For workbook host vetointv.akamaized.net only, the
user approved including dreamboat-ch01vetointv.akamaized.net on the workbook's mapped dates.

All HTTP statuses and request types contribute audience groups. raw_ts_requests counts
only .ts paths across all statuses, without deduplication. Zero-TS groups are kept.
Unknown decoded fields and missing device IDs are retained.
Distinct client IPs must be calculated across the selected dataset, not by adding row counts.

latest_run.json: current date/host, completed mappings, issues and final combined-file path.
receipts/: per-partition count reconciliation, source references and lookup provenance.
runs/: mapping/decode snapshots, staged partition copies, and the combined 12-column
Parquet snapshot produced when a run finishes. Older run files are retained.

Run from the workspace root:
  .\venv\Scripts\python.exe ETL/SportTodo/build_sports_store.py

Repeated runs skip existing completed mappings and append new ones from the workbook.
Changing labels for an existing date/host is flagged for review, not silently rewritten.
Only one writer runs at a time. Missing lake data/hosts are recorded as issues, not zeros.
20 October is a known partial CDN source date: exported retained requests are not full-day totals.
No cleanup or source deletion is performed by this exporter.

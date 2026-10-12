# VETO streaming analytics — damaged SQLite read-only browser

## Windows quick start
1. Extract this folder anywhere (e.g. `D:\veto_dashboard`).
2. Ensure Python 3.14 is available as `python` (or edit `launch.bat` for your exact Python path).
3. Double-click `launch.bat` or use:
   ```powershell
   python -m pip install -r requirements.txt
   python -m streamlit run app.py
   ```
4. Open the localhost URL printed by Streamlit. Default database path is `D:\live_monitor.sqlite3`.
5. `daily_viewers` is selected by default. Set row/page scan caps and click **Scan selected table**.

## Important
- **Read-only**: uses `open(path, 'rb')`. Never calls SQLite engine or writes to the database.
- **No recovery database**: no repair, VACUUM, checkpoint, migration or full export.
- **Bounded RAM**: page walker holds one B-tree page plus individual cell overflow payloads (capped); retains only up to 500 preview rows and aggregate counters. Unique per-viewer exact counting across large scans is deliberately **not** attempted.
- It may scan many pages/rows to find a date or channel; filters are applied as rows are decoded.
- It can skip corrupt pages/cells and cannot traverse disconnected/orphaned B-tree pages. Counts are lower bounds of successfully decoded rows, not authoritative analytics totals.
- Database should not be changing during scans. If writes occur concurrently, seek/read can observe inconsistent pages; use a consistent filesystem snapshot, if possible.
- It uses table root page addresses from readable `sqlite_schema` records and works with ordinary rowid tables only.
- SQLite virtual tables, WITHOUT ROWID tables, and indexes aren't supported by this raw reader.
- Columns based on the user-provided recovered schema: if your app updated its schema, extra fields are labeled `extra_N`.
- A zero-byte WAL contains no pending WAL frames. Do not delete SHM or WAL as part of this workflow.

## Definitions
- `daily_viewers`: one key per date, request host, target and viewer; row count is **not** unique people across channels/hosts.
- `minute_viewers`: analogous at minute granularity.
- `__all__` is an aggregate target; avoid adding it on top of channel totals.
- Raw-page scans bypass sqlite3's corruption error but do **not** guarantee completeness or correctness of all data.

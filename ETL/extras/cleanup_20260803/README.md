# ETL Cleanup - 2026-08-03

This folder contains files confirmed not to be part of the active ETL or
dashboard runtime.

## Code drafts

- `TRASHbuild_asrun_demo.py`: superseded ASRUN generator backup.
- `build_asrun_demo_FINAL_OPTIMIZED.py`: empty proposal placeholder.

## Duplicate inputs

- `ASRUN-150726.txt`: byte-identical to the active copy under
  `ETL/asrun_demo/data/raw/`.

## Sample inputs

- `As Run Logs - MP CM As Run.csv`: unreferenced manual ASRUN sample.
- `As Run Logs - OLD MP CM As Run.csv`: unreferenced older manual sample.

## Generated test artifacts

The `test_artifacts` and `python_caches` folders contain disposable pytest and
Python cache output. They are retained here for inspection but ignored by Git.

Active source code, tests, configuration, Parquet marts, dashboard sidecars,
raw daily ASRUN files, and `distinct_UA_Both_All.csv` were not moved.

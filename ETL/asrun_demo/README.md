# ASRUN Demo

Standalone proof of concept for broadcast ASRUN files. This folder does not run
inside the daily FAST/STREAM ETL yet.

## Folder layout

- `data/raw`: daily ASRUN text files.
- `data/parsed`: normalized Parquet data produced from those files.
- `config/creative_brand_map.csv`: optional manual creative-to-brand mapping.
- `output`: the static stakeholder HTML dashboard and a CSV export.
- `src/build_asrun_demo.py`: parser and dashboard generator.

## Daily standalone run

1. Put each daily file in `data/raw` using exactly `ASRUN-DDMMYY.txt`, for example `ASRUN-160726.txt`.
2. From `ETL`, run:

```powershell
.\asrun_demo\run_demo.ps1 -Channel "Unassigned - stakeholder mapping required"
```

The runner reads every valid daily ASRUN file in `data/raw`, rebuilds the combined
Parquet, CSV, and static HTML dashboard, and overwrites only the demo outputs.
It is fully standalone today; it is not part of the daily FAST/STREAM ETL yet.

To run a specific file manually:

```powershell
.\venv\Scripts\python.exe .\asrun_demo\src\build_asrun_demo.py `
  --input .\asrun_demo\data\raw\ASRUN-150726.txt `
  --channel "Unassigned - stakeholder mapping required"
```

## What counts as an advertisement

Only IDs beginning with `C00` are classified as **Spot** and IDs beginning with
`LBD` as **L-band**. All other ASRUN control, programme, SCTE, GPI and graphics
events are retained in the parsed Parquet but excluded from ad KPIs.

## Important limitation

ASRUN is playout evidence. It can show delivered creative, timestamp and actual
duration. It does not contain a viewer identity or an audience count. A later
ETL implementation can join its IST time windows to FAST or STREAM viewer marts
only after each ASRUN file is assigned to a canonical Veto channel.

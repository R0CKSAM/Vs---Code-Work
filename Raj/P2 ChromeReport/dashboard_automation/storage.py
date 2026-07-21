from __future__ import annotations

from pathlib import Path

import pandas as pd


def append_to_csv(dataframe: pd.DataFrame, csv_path: Path) -> int:
    if dataframe.empty:
        return 0

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    prepared = dataframe.reset_index(drop=True)
    if csv_path.exists() and csv_path.stat().st_size > 0:
        existing = pd.read_csv(csv_path, low_memory=False)
        all_columns = list(dict.fromkeys([*existing.columns.tolist(), *prepared.columns.tolist()]))
        existing = existing.reindex(columns=all_columns)
        prepared = prepared.reindex(columns=all_columns)
        combined = pd.concat([existing, prepared], ignore_index=True)
    else:
        combined = prepared

    combined.to_csv(csv_path, index=False, encoding="utf-8-sig")
    return len(prepared.index)


def load_csv(csv_path: Path, *, dtype: dict[str, str] | None = None) -> pd.DataFrame:
    if not csv_path.exists():
        return pd.DataFrame()
    return pd.read_csv(csv_path, dtype=dtype, keep_default_na=False, na_values=[""], low_memory=False)

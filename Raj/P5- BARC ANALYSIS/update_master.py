from __future__ import annotations

import argparse
import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "Data"
INCOMING_DIR = DATA_DIR / "Incoming"
ARCHIVE_DIR = DATA_DIR / "Archive"
MASTER_XLSX = DATA_DIR / "Master_Data.xlsx"
MASTER_PKL = DATA_DIR / "Master_Data.pkl"

ID_CANDIDATES = (
    "id",
    "record_id",
    "uuid",
    "guid",
    "transaction_id",
    "entry_id",
    "row_id",
)


@dataclass
class LoadResult:
    frame: pd.DataFrame
    source: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Update the master workbook from Excel files dropped into Data/Incoming."
    )
    parser.add_argument(
        "--unique-key",
        nargs="+",
        help="Column(s) used to detect duplicate rows. Falls back to auto-detected ID columns or full-row hashing.",
    )
    parser.add_argument(
        "--seed-file",
        help="Optional workbook used to bootstrap the initial master when Master_Data.xlsx does not yet exist.",
    )
    return parser.parse_args()


def list_incoming_files() -> list[Path]:
    if not INCOMING_DIR.exists():
        return []
    return sorted(
        file
        for file in INCOMING_DIR.glob("*.xlsx")
        if file.is_file() and not file.name.startswith("~$")
    )


def read_workbook(path: Path) -> pd.DataFrame:
    return pd.read_excel(path, sheet_name=0, engine="openpyxl")


def normalize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    cleaned = frame.copy()
    cleaned.columns = [str(col).strip() for col in cleaned.columns]
    return cleaned


def load_master() -> LoadResult | None:
    if MASTER_PKL.exists() and MASTER_XLSX.exists():
        if MASTER_PKL.stat().st_mtime >= MASTER_XLSX.stat().st_mtime:
            return LoadResult(pd.read_pickle(MASTER_PKL), "pickle cache")
    if MASTER_XLSX.exists():
        return LoadResult(read_workbook(MASTER_XLSX), "master workbook")
    return None


def bootstrap_seed(seed_file: str | None) -> Path | None:
    if seed_file:
        candidate = Path(seed_file).expanduser().resolve()
        if not candidate.exists():
            raise FileNotFoundError(f"Seed file not found: {candidate}")
        return candidate

    preferred = DATA_DIR / "Book1.xlsx"
    if preferred.exists():
        return preferred

    for candidate in sorted(DATA_DIR.glob("*.xlsx")):
        if candidate.name not in {MASTER_XLSX.name}:
            return candidate
    return None


def align_to_schema(frame: pd.DataFrame, master_columns: list[str]) -> pd.DataFrame:
    if list(frame.columns) != master_columns:
        missing = [col for col in master_columns if col not in frame.columns]
        extras = [col for col in frame.columns if col not in master_columns]
        details = []
        if missing:
            details.append(f"missing columns: {missing}")
        if extras:
            details.append(f"unexpected columns: {extras}")
        raise ValueError("Incoming schema does not match master schema; " + "; ".join(details))
    return frame.loc[:, master_columns]


def coerce_to_master_dtypes(frame: pd.DataFrame, master: pd.DataFrame) -> pd.DataFrame:
    aligned = frame.copy()
    for column, dtype in master.dtypes.items():
        try:
            if pd.api.types.is_numeric_dtype(dtype):
                aligned[column] = pd.to_numeric(aligned[column], errors="coerce")
            else:
                aligned[column] = aligned[column].astype(dtype, copy=False)
        except TypeError:
            aligned[column] = aligned[column].astype(str)
    return aligned


def choose_dedupe_key(frame: pd.DataFrame, explicit_key: list[str] | None) -> list[str]:
    if explicit_key:
        missing = [column for column in explicit_key if column not in frame.columns]
        if missing:
            raise ValueError(f"Unique key column(s) not found: {missing}")
        return explicit_key

    lowered = {column.lower(): column for column in frame.columns}
    for candidate in ID_CANDIDATES:
        if candidate in lowered:
            return [lowered[candidate]]

    return []


def make_row_signature(frame: pd.DataFrame) -> pd.Series:
    as_text = frame.fillna("").astype(str)
    return as_text.apply(
        lambda row: hashlib.sha1("||".join(row.values.tolist()).encode("utf-8")).hexdigest(),
        axis=1,
    )


def append_only_new_rows(
    master: pd.DataFrame,
    incoming: pd.DataFrame,
    explicit_key: list[str] | None,
) -> tuple[pd.DataFrame, int]:
    key_columns = choose_dedupe_key(master, explicit_key)
    if key_columns:
        master_keys = master[key_columns].fillna("").astype(str).agg("||".join, axis=1)
        incoming_keys = incoming[key_columns].fillna("").astype(str).agg("||".join, axis=1)
    else:
        master_keys = make_row_signature(master)
        incoming_keys = make_row_signature(incoming)

    incoming_new = incoming.loc[~incoming_keys.isin(set(master_keys))].copy()
    combined = pd.concat([master, incoming_new], ignore_index=True)

    if key_columns:
        combined = combined.drop_duplicates(subset=key_columns, keep="first")
    else:
        combined = combined.loc[~make_row_signature(combined).duplicated()].copy()

    return combined, len(incoming_new)


def save_master(frame: pd.DataFrame) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    frame.to_excel(MASTER_XLSX, index=False)
    frame.to_pickle(MASTER_PKL)


def archive_file(path: Path) -> None:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    target = ARCHIVE_DIR / path.name
    counter = 1
    while target.exists():
        target = ARCHIVE_DIR / f"{path.stem}_{counter}{path.suffix}"
        counter += 1
    shutil.move(str(path), str(target))


def main() -> None:
    args = parse_args()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    INCOMING_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    master_result = load_master()

    if master_result is None:
        seed = bootstrap_seed(args.seed_file)
        if seed is None:
            raise FileNotFoundError(
                "Master_Data.xlsx does not exist and no bootstrap workbook was found in Data."
            )
        master = normalize_frame(read_workbook(seed))
        save_master(master)
        master_result = LoadResult(master, f"bootstrap workbook ({seed.name})")
        print(f"Initialized master from {seed}")

    master = normalize_frame(master_result.frame)
    incoming_files = list_incoming_files()

    if not incoming_files:
        save_master(master)
        print(f"No incoming files found. Master is current from {master_result.source}.")
        print(f"Rows: {len(master):,}")
        return

    total_added = 0
    processed = 0
    master_columns = list(master.columns)

    for workbook in incoming_files:
        incoming = normalize_frame(read_workbook(workbook))
        incoming = align_to_schema(incoming, master_columns)
        incoming = coerce_to_master_dtypes(incoming, master)
        master, added = append_only_new_rows(master, incoming, args.unique_key)
        total_added += added
        processed += 1
        archive_file(workbook)
        print(f"Processed {workbook.name}: added {added:,} new rows")

    save_master(master)
    print(f"Updated master rows: {len(master):,}")
    print(f"Files processed: {processed}")
    print(f"Net new rows added: {total_added:,}")


if __name__ == "__main__":
    main()

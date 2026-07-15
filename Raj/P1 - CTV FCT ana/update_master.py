from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd
from pandas.api import types as pdt


DEFAULT_DATA_DIR = Path(__file__).resolve().parent / "Data"
DEFAULT_MASTER_PATH = DEFAULT_DATA_DIR / "Master_Data.xlsx"
DEFAULT_INCOMING_DIR = DEFAULT_DATA_DIR / "Incoming"
DEFAULT_ARCHIVE_DIR = DEFAULT_DATA_DIR / "Archive"
AUTO_ID_CANDIDATES = (
    "id",
    "record_id",
    "unique_id",
    "uuid",
    "transaction_id",
    "row_id",
)
OK_PREFIX = "[OK]"
ERROR_PREFIX = "[ERROR]"


@dataclass
class WorkbookData:
    path: Path
    sheet_name: str
    frame: pd.DataFrame


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create or update a master Excel dataset without changing dashboard behavior."
    )
    parser.add_argument("--master", type=Path, default=DEFAULT_MASTER_PATH, help="Path to Master_Data.xlsx")
    parser.add_argument("--incoming", type=Path, default=DEFAULT_INCOMING_DIR, help="Folder containing new Excel files")
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE_DIR, help="Folder where processed files are moved")
    parser.add_argument(
        "--unique-key",
        nargs="+",
        default=None,
        help="Optional column name(s) used for duplicate detection. Defaults to auto-detection, then full-row comparison.",
    )
    return parser.parse_args()


def log(message: str) -> None:
    print(message)


def log_ok(message: str) -> None:
    log(f"{OK_PREFIX} {message}")


def fail(message: str) -> None:
    print(f"{ERROR_PREFIX} {message}", file=sys.stderr)


def create_folders(*paths: Path) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def list_incoming_files(incoming_dir: Path, master_path: Path) -> list[Path]:
    return sorted(
        path
        for path in incoming_dir.glob("*.xlsx")
        if path.is_file() and not path.name.startswith("~$") and path.resolve() != master_path.resolve()
    )


def read_excel_file(path: Path) -> WorkbookData:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    log_ok(f"Reading {path.name}")

    try:
        excel_file = pd.ExcelFile(path, engine="openpyxl")
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"{path.name} cannot be opened or is not a valid Excel workbook.") from exc

    if not excel_file.sheet_names:
        raise ValueError(f"{path.name} has no sheets.")

    sheet_name = excel_file.sheet_names[0]
    log_ok(f"Using sheet: {sheet_name}")

    try:
        frame = pd.read_excel(path, sheet_name=sheet_name, engine="openpyxl")
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Could not read sheet '{sheet_name}' from {path.name}.") from exc

    return WorkbookData(path=path, sheet_name=sheet_name, frame=frame.dropna(how="all"))


def create_master_dataset(initial_file: Path, master_path: Path) -> WorkbookData:
    workbook = read_excel_file(initial_file)
    if workbook.frame.empty:
        raise ValueError(f"{initial_file.name} does not contain any data rows.")

    log_ok("Master_Data.xlsx not found")
    log_ok("Creating new master dataset")
    save_master_dataset(workbook.frame, master_path, workbook.sheet_name)
    log_ok(f"Added {len(workbook.frame)} rows")
    log_ok("Master_Data.xlsx created successfully")
    return WorkbookData(path=master_path, sheet_name=workbook.sheet_name, frame=workbook.frame.copy())


def load_master_dataset(master_path: Path) -> WorkbookData:
    return read_excel_file(master_path)


def validate_columns(master_columns: list[str], incoming_columns: list[str], file_name: str) -> None:
    if incoming_columns == master_columns:
        return

    master_set = set(master_columns)
    incoming_set = set(incoming_columns)
    missing = [column for column in master_columns if column not in incoming_set]
    extra = [column for column in incoming_columns if column not in master_set]
    details: list[str] = []

    if missing:
        details.append(f"Missing columns: {missing}")
    if extra:
        details.append(f"Extra columns: {extra}")
    if not details:
        details.append("Column order does not match the master dataset")

    raise ValueError(f"{file_name} failed: {'; '.join(details)}")


def align_to_master_schema(master_frame: pd.DataFrame, incoming_frame: pd.DataFrame) -> pd.DataFrame:
    aligned = incoming_frame.loc[:, master_frame.columns].copy()

    for column in master_frame.columns:
        target_dtype = master_frame[column].dtype
        source_series = aligned[column]

        if pdt.is_datetime64_any_dtype(target_dtype):
            aligned[column] = pd.to_datetime(source_series, errors="coerce")
        elif pdt.is_integer_dtype(target_dtype):
            numeric = pd.to_numeric(source_series, errors="coerce")
            if numeric.isna().any() and source_series.notna().any():
                raise ValueError(f"Column '{column}' contains values that cannot be converted to integers.")
            aligned[column] = numeric.astype(target_dtype)
        elif pdt.is_float_dtype(target_dtype):
            numeric = pd.to_numeric(source_series, errors="coerce")
            if numeric.isna().any() and source_series.notna().any():
                raise ValueError(f"Column '{column}' contains values that cannot be converted to numbers.")
            aligned[column] = numeric.astype(target_dtype)
        elif pdt.is_bool_dtype(target_dtype):
            aligned[column] = source_series.astype(target_dtype)
        else:
            try:
                aligned[column] = source_series.astype(target_dtype, copy=False)
            except (TypeError, ValueError):
                aligned[column] = source_series

    return aligned


def auto_detect_unique_key(columns: Iterable[str]) -> list[str] | None:
    lookup = {str(column).strip().lower(): column for column in columns}
    for candidate in AUTO_ID_CANDIDATES:
        if candidate in lookup:
            return [lookup[candidate]]
    return None


def normalize_for_comparison(frame: pd.DataFrame) -> pd.DataFrame:
    comparable = frame.copy()
    for column in comparable.columns:
        series = comparable[column]
        if pdt.is_datetime64_any_dtype(series):
            comparable[column] = pd.to_datetime(series, errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S")
        else:
            comparable[column] = series.map(lambda value: "" if pd.isna(value) else str(value).strip())
    return comparable


def append_new_data(master_frame: pd.DataFrame, incoming_frame: pd.DataFrame, unique_key: list[str] | None) -> tuple[pd.DataFrame, int]:
    if incoming_frame.empty:
        return master_frame.copy(), 0

    unique_columns = unique_key or auto_detect_unique_key(master_frame.columns)

    if unique_columns:
        missing = [column for column in unique_columns if column not in master_frame.columns]
        if missing:
            raise ValueError(f"Unique key column(s) not found in master dataset: {', '.join(missing)}.")

        master_keys = normalize_for_comparison(master_frame.loc[:, unique_columns]).agg("||".join, axis=1)
        incoming_keys = normalize_for_comparison(incoming_frame.loc[:, unique_columns]).agg("||".join, axis=1)
        new_rows = incoming_frame.loc[~incoming_keys.isin(set(master_keys))].copy()
    else:
        master_hash = pd.util.hash_pandas_object(normalize_for_comparison(master_frame), index=False)
        incoming_hash = pd.util.hash_pandas_object(normalize_for_comparison(incoming_frame), index=False)
        new_rows = incoming_frame.loc[~incoming_hash.isin(set(master_hash))].copy()

    if new_rows.empty:
        return master_frame.copy(), 0

    appended = pd.concat([master_frame, new_rows], ignore_index=True)
    return appended.loc[:, master_frame.columns], len(new_rows)


def remove_duplicates(frame: pd.DataFrame, unique_key: list[str] | None) -> tuple[pd.DataFrame, int]:
    unique_columns = unique_key or auto_detect_unique_key(frame.columns)

    if unique_columns:
        comparable = normalize_for_comparison(frame.loc[:, unique_columns])
    else:
        comparable = normalize_for_comparison(frame)

    duplicate_mask = comparable.duplicated(keep="first")
    deduplicated = frame.loc[~duplicate_mask].reset_index(drop=True)
    return deduplicated, int(duplicate_mask.sum())


def save_master_dataset(master_frame: pd.DataFrame, master_path: Path, sheet_name: str) -> None:
    with pd.ExcelWriter(master_path, engine="openpyxl") as writer:
        master_frame.to_excel(writer, sheet_name=sheet_name, index=False)


def archive_processed_file(file_path: Path, archive_dir: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = archive_dir / f"{file_path.stem}_processed_{timestamp}{file_path.suffix}"
    counter = 1

    while destination.exists():
        destination = archive_dir / f"{file_path.stem}_processed_{timestamp}_{counter}{file_path.suffix}"
        counter += 1

    shutil.move(str(file_path), str(destination))
    return destination


def main() -> int:
    args = parse_args()
    create_folders(args.master.parent, args.incoming, args.archive)

    incoming_files = list_incoming_files(args.incoming, args.master)
    unique_key = args.unique_key

    if args.master.exists():
        try:
            log_ok("Existing master dataset found")
            master_workbook = load_master_dataset(args.master)
            master_frame = master_workbook.frame.copy()
        except Exception as exc:  # noqa: BLE001
            fail(str(exc))
            return 1
    else:
        if not incoming_files:
            fail("Master_Data.xlsx not found and Incoming folder does not contain any Excel files.")
            return 1

        first_file = incoming_files[0]
        try:
            master_workbook = create_master_dataset(first_file, args.master)
            master_frame = master_workbook.frame.copy()
            archived = archive_processed_file(first_file, args.archive)
            log_ok(f"Archived {archived.name}")
        except Exception as exc:  # noqa: BLE001
            fail(str(exc))
            return 1

        incoming_files = incoming_files[1:]

    if not incoming_files:
        log_ok("No new Excel files found in Incoming. Master dataset is already up to date.")
        return 0

    for file_path in incoming_files:
        try:
            incoming_workbook = read_excel_file(file_path)
            validate_columns(list(master_frame.columns), list(incoming_workbook.frame.columns), file_path.name)
            log_ok("Appending new records")
            aligned_incoming = align_to_master_schema(master_frame, incoming_workbook.frame)
            updated_master, appended_count = append_new_data(master_frame, aligned_incoming, unique_key)
            deduplicated_master, removed_duplicates = remove_duplicates(updated_master, unique_key)
            save_master_dataset(deduplicated_master, args.master, master_workbook.sheet_name)
            master_frame = deduplicated_master
            log_ok(f"Added {appended_count} new rows")
            log_ok(f"Removed {removed_duplicates} duplicate rows")
            log_ok("Master_Data.xlsx updated successfully")
            archived = archive_processed_file(file_path, args.archive)
            log_ok(f"Archived {archived.name}")
        except Exception as exc:  # noqa: BLE001
            fail(str(exc))
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

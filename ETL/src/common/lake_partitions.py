"""Helpers for reading the active lake plus optional archive lake roots.

The ETL can move older lake days to slower/archive storage.  These helpers
resolve one winning partition per source/date so dashboards can read the full
history without double-counting dates that exist in both current and archive
roots.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable


ARCHIVE_ENV_NAMES = (
    "VG_ETL_ARCHIVE_LAKE_ROOTS",
    "VG_ETL_ARCHIVE_LAKE_ROOT",
    "VG_ARCHIVE_LAKE_ROOTS",
    "VG_ARCHIVE_LAKE_ROOT",
)


@dataclass(frozen=True)
class LakePartition:
    source: str
    year: int
    month: int
    day: int
    root: Path
    day_dir: Path
    files: tuple[Path, ...]
    priority: int

    @property
    def date_text(self) -> str:
        return f"{self.year:04d}-{self.month:02d}-{self.day:02d}"

    @property
    def key(self) -> str:
        return f"{self.source}/{self.date_text}"


def split_path_list(value: str | None) -> list[Path]:
    """Parse comma/semicolon separated roots.

    We intentionally do not split on ``os.pathsep`` because Windows drive
    letters contain ``:``.
    """
    if not value:
        return []
    parts = [part.strip().strip('"') for part in re.split(r"[;,]", value) if part.strip()]
    return [Path(part).expanduser() for part in parts]


def env_archive_roots() -> list[Path]:
    roots: list[Path] = []
    for name in ARCHIVE_ENV_NAMES:
        roots.extend(split_path_list(os.getenv(name)))
    default_z = Path(r"Z:\Veto Logs Backup\DO NOT DELETE")
    if default_z.exists():
        roots.append(default_z)
    return roots


def resolve_lake_roots(primary: Path, archive_roots: Iterable[Path] | None = None) -> list[Path]:
    """Return readable lake roots in priority order, current first."""
    roots = [primary]
    roots.extend(archive_roots or env_archive_roots())
    resolved: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        try:
            path = Path(root).expanduser().resolve()
        except OSError:
            continue
        key = str(path).lower()
        if key in seen or not path.exists():
            continue
        seen.add(key)
        resolved.append(path)
    return resolved


def _date_in_range(date_value: date, start: date | None, end: date | None) -> bool:
    if start and date_value < start:
        return False
    if end and date_value > end:
        return False
    return True


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def _parts_from_day_dir(day_dir: Path) -> tuple[str, int, int, int] | None:
    values = {part.split("=", 1)[0].lower(): part.split("=", 1)[1] for part in day_dir.parts if "=" in part}
    if {"year", "month", "day"} - set(values):
        return None
    try:
        source = values.get("source", "stream").lower()
        return source, int(values["year"]), int(values["month"]), int(values["day"])
    except ValueError:
        return None


def _safe_partition_row_count(files: tuple[Path, ...]) -> int:
    """Return parquet metadata rows without scanning data columns.

    Current lake can contain partial duplicate partitions while the archive has
    the completed day. Row-count metadata gives us a cheap completeness signal
    so we do not blindly choose an incomplete current partition.
    """
    try:
        import pyarrow.parquet as pq
    except Exception:
        return 0
    total = 0
    for file in files:
        try:
            total += int(pq.read_metadata(file).num_rows or 0)
        except Exception:
            continue
    return total


def _partition_score(partition: LakePartition) -> tuple[int, int, int]:
    """Higher score wins; lower priority wins only when completeness ties."""
    return (
        _safe_partition_row_count(partition.files),
        len(partition.files),
        -partition.priority,
    )


def _source_dirs(root: Path, allowed_sources: set[str] | None) -> list[Path]:
    dirs = sorted(path for path in root.glob("source=*") if path.is_dir())
    if allowed_sources is None:
        return dirs
    return [path for path in dirs if path.name.split("=", 1)[-1].lower() in allowed_sources]


def discover_partitions(
    lake_roots: Iterable[Path],
    *,
    source: str | None = None,
    sources: Iterable[str] | None = None,
    year: str | int | None = None,
    month: str | int | None = None,
    start: str | date | None = None,
    end: str | date | None = None,
) -> list[LakePartition]:
    """Discover one winning partition per source/date across current/archive roots."""
    allowed_sources = {str(item).lower().removeprefix("source=") for item in sources or [] if str(item).strip()}
    if source:
        allowed_sources.add(str(source).lower().removeprefix("source="))
    source_filter = allowed_sources or None
    year_filter = f"{int(year):04d}" if year else None
    month_filter = f"{int(month):02d}" if month else None
    start_date = start if isinstance(start, date) else parse_date(start)
    end_date = end if isinstance(end, date) else parse_date(end)

    selected: dict[tuple[str, str], LakePartition] = {}
    for priority, raw_root in enumerate(lake_roots):
        root = Path(raw_root)
        if not root.exists():
            continue
        scan_roots: list[Path] = []
        for source_dir in _source_dirs(root, source_filter):
            candidate = source_dir
            if year_filter:
                candidate = candidate / f"year={year_filter}"
            if month_filter:
                candidate = candidate / f"month={month_filter}"
            if candidate.exists():
                scan_roots.append(candidate)
        if not scan_roots and source_filter is None:
            candidate = root
            if year_filter:
                candidate = candidate / f"year={year_filter}"
            if month_filter:
                candidate = candidate / f"month={month_filter}"
            if candidate.exists():
                scan_roots.append(candidate)

        for scan_root in scan_roots:
            for day_dir in sorted(scan_root.rglob("day=*")):
                parsed = _parts_from_day_dir(day_dir)
                if parsed is None:
                    continue
                source_name, yy, mm, dd = parsed
                if source_filter is not None and source_name not in source_filter:
                    continue
                day_value = date(yy, mm, dd)
                if not _date_in_range(day_value, start_date, end_date):
                    continue
                files = tuple(sorted(day_dir.glob("*.parquet")))
                if not files:
                    continue
                date_text = f"{yy:04d}-{mm:02d}-{dd:02d}"
                key = (source_name, date_text)
                candidate = LakePartition(source_name, yy, mm, dd, root, day_dir, files, priority)
                existing = selected.get(key)
                if existing is not None and _partition_score(candidate) <= _partition_score(existing):
                    continue
                selected[key] = candidate

    return sorted(selected.values(), key=lambda p: (p.year, p.month, p.day, p.source))


def partition_for_date(lake_roots: Iterable[Path], source: str, date_text: str) -> LakePartition | None:
    partitions = discover_partitions(lake_roots, source=source, start=date_text, end=date_text)
    return partitions[0] if partitions else None


def parquet_globs(partitions: Iterable[LakePartition]) -> list[str]:
    return [str(part.day_dir / "*.parquet").replace("\\", "/").replace("'", "''") for part in partitions]

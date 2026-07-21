from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import DashboardAutomationConfig
from .logging_utils import configure_logging
from .readers import read_distribution_details, read_nbhd_details, read_ots_summary
from .state import is_processed, load_processed_state, mark_processed, save_processed_state
from .storage import append_to_csv, load_csv
from .utils import compute_file_hash, extract_week_label, list_candidate_files, wait_for_file_ready


@dataclass(slots=True)
class ProcessSummary:
    processed: int = 0
    skipped: int = 0
    failed: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "processed": self.processed,
            "skipped": self.skipped,
            "failed": self.failed,
        }


class HistoricalDatasetStore:
    def __init__(self, config: DashboardAutomationConfig) -> None:
        self.config = config

    def append_weekly_data(self, distribution: pd.DataFrame, nbhd: pd.DataFrame, ots: pd.DataFrame) -> dict[str, int]:
        return {
            "distribution": append_to_csv(distribution, self.config.distribution_csv),
            "nbhd": append_to_csv(nbhd, self.config.nbhd_csv),
            "ots": append_to_csv(ots, self.config.ots_csv),
        }

    def load_dashboard_frames(self) -> dict[str, pd.DataFrame]:
        return {
            "distribution": load_csv(self.config.distribution_csv),
            "nbhd": load_csv(self.config.nbhd_csv),
            "ots": load_csv(self.config.ots_csv),
        }


class WeeklyWorkbookProcessor:
    def __init__(self, config: DashboardAutomationConfig, store: HistoricalDatasetStore, logger: logging.Logger) -> None:
        self.config = config
        self.store = store
        self.logger = logger

    def process_file(self, file_path: Path) -> dict[str, int]:
        week_label = extract_week_label(file_path.name)
        self.logger.info("Processing %s as %s", file_path.name, week_label)

        distribution = read_distribution_details(file_path, week_label)
        nbhd = read_nbhd_details(file_path, week_label)
        ots = read_ots_summary(file_path, week_label)
        row_counts = self.store.append_weekly_data(distribution, nbhd, ots)

        self.logger.info(
            "Completed %s | distribution=%s nbhd=%s ots=%s",
            file_path.name,
            row_counts["distribution"],
            row_counts["nbhd"],
            row_counts["ots"],
        )
        return row_counts


class DashboardUpdatePipeline:
    def __init__(self, config: DashboardAutomationConfig, logger: logging.Logger | None = None) -> None:
        self.config = config
        self.config.ensure_directories()
        self.logger = logger or configure_logging(config)
        self.store = HistoricalDatasetStore(config)
        self.processor = WeeklyWorkbookProcessor(config, self.store, self.logger)

    def run(self, file_paths: list[Path] | None = None) -> dict[str, Any]:
        history_ready = self._history_files_ready()
        state = load_processed_state(self.config.processed_files_path) if history_ready else {"version": 1, "processed_files": {}}
        candidates = self._resolve_candidates(file_paths)
        summary = ProcessSummary()

        for file_path in candidates:
            try:
                wait_for_file_ready(file_path)
                fingerprint = compute_file_hash(file_path)
                if history_ready and is_processed(state, fingerprint):
                    summary.skipped += 1
                    self.logger.info("Skipping already processed file: %s", file_path.name)
                    continue

                row_counts = self.processor.process_file(file_path)
                mark_processed(state, fingerprint, file_path, extract_week_label(file_path.name), row_counts)
                save_processed_state(self.config.processed_files_path, state)
                summary.processed += 1
            except Exception as error:  # noqa: BLE001
                summary.failed += 1
                self.logger.exception("Failed to process %s: %s", file_path.name, error)

        from app import generate_frequency_report_json

        json_path = generate_frequency_report_json()
        result = {
            **summary.as_dict(),
            "frequency_report_json": str(json_path),
            "dashboard_html": str(self.config.dashboard_html),
            "distribution_csv": str(self.config.distribution_csv),
            "nbhd_csv": str(self.config.nbhd_csv),
            "ots_csv": str(self.config.ots_csv),
        }
        self.logger.info(
            "Run complete | processed=%s skipped=%s failed=%s json=%s",
            result["processed"],
            result["skipped"],
            result["failed"],
            result["frequency_report_json"],
        )
        return result

    def _resolve_candidates(self, file_paths: list[Path] | None) -> list[Path]:
        if file_paths is None:
            return list_candidate_files(self.config.data_dir, self.config.supported_extensions)
        return sorted({path.resolve() for path in file_paths if path.exists()}, key=lambda path: path.name.lower())

    def _history_files_ready(self) -> bool:
        history_paths = [
            self.config.distribution_csv,
            self.config.nbhd_csv,
            self.config.ots_csv,
        ]
        ready = all(path.exists() and path.stat().st_size > 0 for path in history_paths)
        if not ready:
            self.logger.info("Historical CSV files missing or empty. Rebuilding history from source workbooks.")
        return ready


def process_new_files(
    config: DashboardAutomationConfig,
    logger: logging.Logger | None = None,
    file_paths: list[Path] | None = None,
) -> dict[str, Any]:
    pipeline = DashboardUpdatePipeline(config=config, logger=logger)
    return pipeline.run(file_paths=file_paths)

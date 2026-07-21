from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class DashboardAutomationConfig:
    base_dir: Path
    supported_extensions: tuple[str, ...] = (".xlsm",)
    data_dir: Path = field(init=False)
    history_dir: Path = field(init=False)
    logs_dir: Path = field(init=False)
    distribution_csv: Path = field(init=False)
    nbhd_csv: Path = field(init=False)
    ots_csv: Path = field(init=False)
    processed_files_path: Path = field(init=False)
    output_dir: Path = field(init=False)
    frequency_report_json: Path = field(init=False)
    dashboard_html: Path = field(init=False)
    log_path: Path = field(init=False)
    legacy_distribution_csv: Path = field(init=False)
    legacy_nbhd_csv: Path = field(init=False)
    legacy_ots_csv: Path = field(init=False)

    def __post_init__(self) -> None:
        self.base_dir = self.base_dir.resolve()
        self.data_dir = self.base_dir / "data"
        self.history_dir = self.base_dir / "history"
        self.logs_dir = self.base_dir / "logs"
        self.output_dir = self.base_dir / "output"
        self.distribution_csv = self.history_dir / "distribution_history.csv"
        self.nbhd_csv = self.history_dir / "nbhd_history.csv"
        self.ots_csv = self.history_dir / "ots_history.csv"
        self.processed_files_path = self.base_dir / "processed_files.json"
        self.frequency_report_json = self.output_dir / "frequency_report.json"
        self.dashboard_html = self.output_dir / "chrome_report_dashboard.html"
        self.log_path = self.logs_dir / "dashboard_automation.log"
        self.legacy_distribution_csv = self.base_dir / "distribution_history.csv"
        self.legacy_nbhd_csv = self.base_dir / "nbhd_history.csv"
        self.legacy_ots_csv = self.base_dir / "ots_history.csv"

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

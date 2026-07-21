from __future__ import annotations

import logging
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from .config import DashboardAutomationConfig
from .pipeline import process_new_files


class DashboardFileHandler(FileSystemEventHandler):
    def __init__(self, config: DashboardAutomationConfig, logger: logging.Logger) -> None:
        self.config = config
        self.logger = logger

    def _handle_path(self, file_path: Path) -> None:
        if file_path.suffix.lower() not in {extension.lower() for extension in self.config.supported_extensions}:
            return
        if file_path.name.startswith("~$"):
            return
        process_new_files(self.config, logger=self.logger, file_paths=[file_path])

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._handle_path(Path(event.src_path))

    def on_moved(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._handle_path(Path(event.dest_path))


def watch_data_folder(config: DashboardAutomationConfig, logger: logging.Logger) -> None:
    observer = Observer()
    handler = DashboardFileHandler(config, logger)
    observer.schedule(handler, str(config.data_dir), recursive=False)
    observer.start()
    logger.info("Watching %s for new files...", config.data_dir)
    try:
        observer.join()
    except KeyboardInterrupt:
        logger.info("Stopping watcher...")
        observer.stop()
        observer.join()

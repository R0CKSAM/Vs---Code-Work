from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .config import DashboardAutomationConfig


LOGGER_NAME = "dashboard_automation"


def configure_logging(config: DashboardAutomationConfig) -> logging.Logger:
    config.ensure_directories()

    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    file_handler = RotatingFileHandler(
        config.log_path,
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger

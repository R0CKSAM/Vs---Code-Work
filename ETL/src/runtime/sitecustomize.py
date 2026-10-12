"""Loaded only by workers whose launcher includes this runtime directory."""

import os

from etl_runtime import configure_windows_platform


if os.getenv("VG_ETL_BASE"):
    configure_windows_platform()

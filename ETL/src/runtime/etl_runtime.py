"""Process-local startup guards for the ETL's Python workers."""

import os
import platform
from pathlib import Path
import sys


def configure_windows_platform() -> bool:
    if sys.platform != "win32" or os.getenv("VG_ETL_DISABLE_WMI", "1") == "0":
        return False
    if not hasattr(platform, "_wmi"):
        return False
    # CPython 3.13 can block pandas imports on an unhealthy WMI service.
    # None selects platform's Win32/registry fallback without changing OS services.
    platform._wmi = None
    return True


def worker_environment(env: dict[str, str]) -> dict[str, str]:
    result = dict(env)
    runtime_dir = str(Path(__file__).resolve().parent)
    paths = [p for p in result.get("PYTHONPATH", "").split(os.pathsep) if p]
    if runtime_dir not in paths:
        paths.insert(0, runtime_dir)
    result["PYTHONPATH"] = os.pathsep.join(paths)
    return result

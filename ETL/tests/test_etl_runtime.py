import os
from pathlib import Path
import subprocess
import sys

import pytest


RUNTIME = Path(__file__).resolve().parents[1] / "src" / "runtime"
sys.path.insert(0, str(RUNTIME))
import etl_runtime


def test_windows_uses_platform_fallback(monkeypatch):
    monkeypatch.setattr(etl_runtime.sys, "platform", "win32")
    monkeypatch.setattr(etl_runtime.platform, "_wmi", object(), raising=False)
    monkeypatch.delenv("VG_ETL_DISABLE_WMI", raising=False)
    assert etl_runtime.configure_windows_platform()
    assert etl_runtime.platform._wmi is None


@pytest.mark.parametrize("system,opt_out", [("linux", "1"), ("win32", "0")])
def test_other_process_modes_are_unchanged(monkeypatch, system, opt_out):
    marker = object()
    monkeypatch.setattr(etl_runtime.sys, "platform", system)
    monkeypatch.setattr(etl_runtime.platform, "_wmi", marker, raising=False)
    monkeypatch.setenv("VG_ETL_DISABLE_WMI", opt_out)
    assert not etl_runtime.configure_windows_platform()
    assert etl_runtime.platform._wmi is marker


def test_worker_environment_preserves_existing_paths():
    original = {"PYTHONPATH": "existing", "VG_ETL_BASE": "example"}
    result = etl_runtime.worker_environment(original)
    assert result["PYTHONPATH"].split(os.pathsep) == [str(RUNTIME), "existing"]
    assert etl_runtime.worker_environment(result) == result
    assert original["PYTHONPATH"] == "existing"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows platform fallback")
def test_real_worker_imports_pandas_without_wmi():
    env = etl_runtime.worker_environment(dict(os.environ, VG_ETL_BASE="test"))
    env.pop("VG_ETL_DISABLE_WMI", None)
    result = subprocess.run(
        [sys.executable, "-c", "import platform; assert platform._wmi is None; "
         "import pandas; assert platform.machine(); print('ready')"],
        env=env, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "ready" in result.stdout

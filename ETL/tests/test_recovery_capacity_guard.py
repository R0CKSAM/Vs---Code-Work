import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

SPEC = importlib.util.spec_from_file_location(
    "capacity_guard", Path(__file__).resolve().parents[1] / "src/tools/recovery_capacity_guard.py")
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)


def test_dependency_missing_is_optional(tmp_path):
    assert guard.dependency_ready(tmp_path / "absent.json")


@pytest.mark.parametrize("status,expected", [("running", False), ("finished", True)])
def test_dependency_status(tmp_path, status, expected):
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"status": status}))
    request = tmp_path / "dependency.json"
    request.write_text(json.dumps({"state_path": str(state), "success_statuses": ["finished"]}))
    assert guard.dependency_ready(request) is expected


def test_failed_or_missing_required_state_is_not_success(tmp_path):
    state = tmp_path / "state.json"
    request = tmp_path / "dependency.json"
    request.write_text(json.dumps({"state_path": str(state), "success_statuses": ["finished"]}))
    with pytest.raises(OSError):
        guard.dependency_ready(request)
    state.write_text('{"status":"failed"}')
    with pytest.raises(RuntimeError):
        guard.dependency_ready(request)


@pytest.mark.parametrize("free", [(49, 200), (60, 99)])
def test_either_volume_low_blocks(free):
    with patch.object(guard.shutil, "disk_usage", side_effect=[SimpleNamespace(free=n * 1024**3) for n in free]):
        with pytest.raises(RuntimeError, match="reserve required"):
            guard.check_capacity(Path("D:/"), Path("Z:/"), 50, 100)


def test_both_reserves_pass():
    with patch.object(guard.shutil, "disk_usage", return_value=SimpleNamespace(free=200 * 1024**3)):
        assert len(guard.check_capacity(Path("D:/"), Path("Z:/"), 50, 100)) == 2


def test_unavailable_volume_fails_closed():
    with patch.object(guard.shutil, "disk_usage", side_effect=OSError("offline")):
        with pytest.raises(OSError):
            guard.check_capacity(Path("D:/"), Path("Z:/"), 50, 100)

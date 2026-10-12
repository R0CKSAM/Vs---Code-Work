"""
test_monitor_cli.py – Unit tests for run_monitor CLI commands, flags, and exit codes (Phase 11).
"""

from __future__ import annotations

import subprocess
import sys
from unittest.mock import patch
import pytest

from app.monitor.models import ExitCode
from run_monitor import main, parse_args


class TestMonitorCLI:
    def test_parse_args_defaults(self):
        with patch.object(sys, "argv", ["run_monitor.py"]):
            args = parse_args()
            assert args.once is False
            assert args.dry_run is False
            assert args.show_status is False
            assert args.show_diagnostics is False
            assert args.do_cleanup is False
            assert args.confirm_yes is False

    def test_parse_args_phase11_flags(self):
        with patch.object(sys, "argv", ["run_monitor.py", "--health", "--diagnostics", "--cleanup", "--yes"]):
            args = parse_args()
            assert args.show_status is True
            assert args.show_diagnostics is True
            assert args.do_cleanup is True
            assert args.confirm_yes is True

    def test_cli_health_command(self):
        with patch.object(sys, "argv", ["run_monitor.py", "--health"]):
            code = main()
            assert code == int(ExitCode.SUCCESS)

    def test_cli_diagnostics_command(self):
        with patch.object(sys, "argv", ["run_monitor.py", "--diagnostics"]):
            code = main()
            assert code == int(ExitCode.SUCCESS)

    def test_cli_cleanup_dry_run_command(self):
        with patch.object(sys, "argv", ["run_monitor.py", "--cleanup", "--dry-run"]):
            code = main()
            assert code == int(ExitCode.SUCCESS)

    def test_cli_cleanup_without_yes_refuses_destructive(self):
        with patch.object(sys, "argv", ["run_monitor.py", "--cleanup"]):
            code = main()
            assert code == int(ExitCode.PARTIAL)

    def test_cli_cleanup_with_yes_executes(self):
        with patch.object(sys, "argv", ["run_monitor.py", "--cleanup", "--yes"]):
            code = main()
            assert code == int(ExitCode.SUCCESS)

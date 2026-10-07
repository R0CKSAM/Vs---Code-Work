import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src' / 'orchestrator'))
from run_pipeline import _process_is_running


class ProcessProbeTest(unittest.TestCase):
    def test_current_process_survives_probe(self):
        self.assertTrue(_process_is_running(os.getpid()))

    def test_invalid_pid_is_absent(self):
        self.assertFalse(_process_is_running(-1))
        self.assertFalse(_process_is_running(0))

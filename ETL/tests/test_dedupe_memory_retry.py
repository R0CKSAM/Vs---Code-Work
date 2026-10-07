import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('dedupe_stage', Path(__file__).resolve().parents[1] / 'src' / 'pipeline' / '02.py')
stage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage)


class DedupeMemoryRetryTest(unittest.TestCase):
    def test_success_keeps_fast_settings(self):
        con, output = Mock(), Mock()
        with patch.object(stage,'dedupe_bucketed',return_value='ok') as run:
            self.assertEqual(stage.dedupe_bucketed_adaptive(con,'input',output,8),'ok')
            self.assertEqual(run.call_count,1)
            con.execute.assert_not_called()

    def test_oom_retries_smaller_buckets(self):
        con, output = Mock(), Mock()
        with patch.object(stage,'dedupe_bucketed',side_effect=[RuntimeError('Out of Memory Error'), 'ok']) as run:
            self.assertEqual(stage.dedupe_bucketed_adaptive(con,'input',output,8),'ok')
            self.assertEqual([call.args[-1] for call in run.call_args_list],[8,32])
            con.execute.assert_called_once()

    def test_no_retry_for_other_errors_and_oom_is_bounded(self):
        for error, count in [('disk full',1),('allocation failure',3)]:
            with patch.object(stage,'dedupe_bucketed',side_effect=RuntimeError(error)) as run:
                with self.assertRaises(RuntimeError):
                    stage.dedupe_bucketed_adaptive(Mock(),'input',Mock(),8)
                self.assertEqual(run.call_count,count)

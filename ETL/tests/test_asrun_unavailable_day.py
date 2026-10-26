import unittest
from unittest.mock import Mock, patch

import pandas as pd

from ETL.asrun_demo.src.build_asrun_demo import validate_asrun_viewer_coverage
from ETL.asrun_demo.src.io_utils import source_file_fingerprint


class UnavailableAudienceDayTests(unittest.TestCase):
    def setUp(self):
        self.events = pd.DataFrame({
            'is_ad': [True],
            'on_air_start_ist': pd.to_datetime(['2026-10-25 12:00:00']),
        })
        self.viewer = pd.DataFrame({
            'source': ['fast', 'fast'],
            'minute_ist': pd.to_datetime(['2026-10-25 00:00:00', '2026-10-25 23:59:00']),
        })

    def test_default_rejects_missing_stream(self):
        with self.assertRaises(RuntimeError):
            validate_asrun_viewer_coverage(self.events, self.viewer)

    def test_explicit_stream_date_is_allowed(self):
        validate_asrun_viewer_coverage(self.events, self.viewer, {('stream', '2026-10-25')})

    def test_other_date_does_not_bypass_guard(self):
        with self.assertRaises(RuntimeError):
            validate_asrun_viewer_coverage(self.events, self.viewer, {('stream', '2026-10-24')})

    def test_fast_still_requires_coverage(self):
        with self.assertRaises(RuntimeError):
            validate_asrun_viewer_coverage(self.events, self.viewer.iloc[:1], {('stream', '2026-10-25')})

    def test_transient_network_stat_retries(self):
        error = OSError('network')
        error.winerror = 59
        path = Mock()
        path.stat.side_effect = [error, Mock(st_size=12, st_mtime_ns=34)]
        with patch('ETL.asrun_demo.src.io_utils.time.sleep'):
            self.assertEqual(source_file_fingerprint(path), {'size': 12, 'mtime_ns': 34})
        self.assertEqual(path.stat.call_count, 2)

    def test_missing_file_is_not_hidden(self):
        path = Mock()
        path.stat.side_effect = FileNotFoundError('missing')
        with self.assertRaises(FileNotFoundError):
            source_file_fingerprint(path)
        self.assertEqual(path.stat.call_count, 1)


if __name__ == '__main__':
    unittest.main()

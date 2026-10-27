import json
from pathlib import Path
import tempfile
import unittest

import duckdb
from ETL.src.tools.check_daily_run_completion import check


class CompletionTests(unittest.TestCase):
    def test_failure_cannot_be_hidden_by_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state = root / 'output/state'
            state.mkdir(parents=True)
            run = dict(target_date='2026-10-25', run_id='r1', started_at='2026-10-26',
                       finished_at='2026-10-27', status='failed',
                       steps=[dict(step='manifest', status='failed')])
            (state / 'pipeline_run_r1.json').write_text(json.dumps(run))
            with self.assertRaises(ValueError):
                check(root, '2026-10-25')
            repair = state / 'reporting_repairs'
            repair.mkdir()
            log = root / 'output/repair.log'
            log.write_text('repair_exit_code=0')
            receipt = dict(status='complete', run_id='r1', repaired_steps=['manifest'], logs={'manifest': str(log)})
            (repair / '2026-10-25.json').write_text(json.dumps(receipt))
            check(root, '2026-10-25')
            receipt['run_id'] = 'wrong'
            (repair / '2026-10-25.json').write_text(json.dumps(receipt))
            with self.assertRaises(ValueError):
                check(root, '2026-10-25')

    def test_min_matches_ordered_hostname_selection(self):
        with duckdb.connect() as con:
            old, new = con.execute("SELECT any_value(host ORDER BY host), min(host) FROM (VALUES ('z'),('a'),(''),('a')) t(host)").fetchone()
            self.assertEqual(old, new)


if __name__ == '__main__':
    unittest.main()

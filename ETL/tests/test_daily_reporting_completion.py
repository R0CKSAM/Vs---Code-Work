import json
from pathlib import Path
import tempfile
import unittest

import duckdb
from ETL.src.tools.check_daily_run_completion import check


class CompletionTests(unittest.TestCase):
    def test_review_retention_does_not_block_but_real_failures_do(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state = root / 'output/state'
            state.mkdir(parents=True)
            reports = root / 'output/validation/daily_delivery'
            reports.mkdir(parents=True)
            log = root / 'output/cleanup.log'
            log.write_text('Cleanup refused: a full PASS validation report is required.')
            run = dict(target_date='2026-10-29', started_at='2026-10-30T06:00:00',
                       finished_at='2026-10-30T18:00:00', status='complete_with_warnings',
                       steps=[dict(step='daily_intermediate_cleanup', status='failed',
                                   allow_failure=True, log_path=str(log))])
            report = dict(date='2026-10-29', mode='full', overall_status='REVIEW',
                          generated_at_ist='2026-10-30T11:00:00+05:30', hard_failure_count=0,
                          source_results=[dict(source=s, status='PASS', selected=dict(full_day=True)) for s in ['fast', 'stream']],
                          profile_reconciliation=[dict(source=s, status='PASS', delta_rows=0) for s in ['fast', 'stream']])
            run_path = state / 'pipeline_run_test.json'
            report_path = reports / 'daily_delivery_validation_2026-10-29_full.json'
            run_path.write_text(json.dumps(run))
            report_path.write_text(json.dumps(report))
            check(root, '2026-10-29')
            for field, value in [('hard_failure_count', 1), ('generated_at_ist', '2026-10-28T11:00:00'), ('overall_status', 'FAIL')]:
                invalid = dict(report, **{field: value})
                report_path.write_text(json.dumps(invalid))
                with self.assertRaises(ValueError):
                    check(root, '2026-10-29')
            report_path.write_text(json.dumps(report))
            log.write_text('Permission denied')
            with self.assertRaises(ValueError):
                check(root, '2026-10-29')
            log.write_text('Cleanup refused: a full PASS validation report is required.')
            run['steps'].append(dict(step='dashboard', status='failed'))
            run_path.write_text(json.dumps(run))
            with self.assertRaises(ValueError):
                check(root, '2026-10-29')

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

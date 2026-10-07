import json
from datetime import date
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src' / 'tools'))
import resume_pending_cleanups as recovery
from resume_pending_cleanups import pending_manifests, reconcile_cleanup_run


class PendingCleanupTests(unittest.TestCase):
    def test_archive_runs_even_when_cleanup_already_finished(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            args=['recovery','--etl-root',folder,'--archive-lake',str(root/'archive'),
                  '--archive-through','2020-01-01','--execute']
            with patch.object(sys,'argv',args), patch.object(recovery.subprocess,'run') as run:
                recovery.main()
            self.assertEqual(run.call_count,2)
            self.assertIn('archive_lake_partitions.py',run.call_args_list[0].args[0][2])
            self.assertNotIn('--execute',run.call_args_list[0].args[0])
            self.assertIn('--execute',run.call_args_list[1].args[0])

    def test_archive_failure_prevents_completion_reconciliation(self):
        with tempfile.TemporaryDirectory() as folder:
            args=['recovery','--etl-root',folder,'--archive-lake',str(Path(folder)/'archive'),
                  '--archive-through','2020-01-01','--execute']
            with patch.object(sys,'argv',args), patch.object(recovery.subprocess,'run',side_effect=RuntimeError('network unavailable')), patch.object(recovery,'reconcile_cleanup_run') as finish:
                with self.assertRaises(RuntimeError):
                    recovery.main()
                finish.assert_not_called()

    def test_reconcile_requires_completed_final_cleanup_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            state = root / 'output' / 'state'
            audit = root / 'output' / 'cleanup'
            state.mkdir(parents=True)
            audit.mkdir(parents=True)
            run = dict(status='running',run_id='20261007_121148',target_date='2026-10-06',
                       args=dict(cleanup_daily_intermediates=True),steps=[dict(step='watch_hours_dashboard_html',status='ok',finished_at='2026-10-07T13:54:15')])
            path = state / 'pipeline_last_run.json'
            path.write_text(json.dumps(run))
            manifest = audit / 'cleanup_2026-10-06_01.json'
            evidence = dict(mode='execute',status='running',started_at_ist='2026-10-07T14:00:00+05:30',finished_at_ist='2026-10-07T14:10:00+05:30')
            manifest.write_text(json.dumps(evidence))
            reconcile_cleanup_run(root,audit)
            self.assertEqual(json.loads(path.read_text())['status'],'running')
            evidence['status']='complete'
            manifest.write_text(json.dumps(evidence))
            reconcile_cleanup_run(root,audit)
            result=json.loads(path.read_text())
            self.assertEqual(result['status'],'complete')
            self.assertEqual(result['steps'][-1]['step'],'daily_intermediate_cleanup')

    def test_latest_execute_status_controls_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for suffix, status, mode in [('01','planned','execute'),('02','complete','execute'),('03','planned','dry-run')]:
                (root / f'cleanup_2026-10-06_{suffix}.json').write_text(json.dumps(dict(date='2026-10-06',status=status,mode=mode)))
            self.assertEqual(pending_manifests(root,date(2026,10,7)), [])

    def test_recent_interruption_only(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for day in ['2025-10-06','2026-10-06','2026-10-07']:
                (root / f'cleanup_{day}_01.json').write_text(json.dumps(dict(date=day,status='running',mode='execute')))
            result = pending_manifests(root,date(2026,10,7))
            self.assertEqual([payload['date'] for _,payload in result], ['2026-10-06'])

    def test_partial_failure_can_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'cleanup_2026-10-06_01.json').write_text(json.dumps(dict(date='2026-10-06',status='partial-failure',mode='execute')))
            self.assertEqual(len(pending_manifests(root,date(2026,10,7))), 1)

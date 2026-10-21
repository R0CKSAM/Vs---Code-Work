import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/tools'))
import resume_failed_lake as resume


class ResumeLakeTest(unittest.TestCase):
    def test_final_requires_matching_dedupe_rows_and_verified_downloads(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base = root / 'data'
            checkpoints = root / 'output/state/downloads'
            checkpoints.mkdir(parents=True)
            records = {}
            day = dt.date(2026, 10, 18)
            for source in ('fast', 'stream'):
                key = f'{source}_2026_10_18'
                folder = base / f'stage/final_clean/source={source}/year=2026/month=10/day=18'
                folder.mkdir(parents=True)
                pq.write_table(pa.table({'reqTimeSec': [1, 2]}), folder / f'{key}_final_clean.parquet')
                records[key] = dict(status='ok', rows=2)
                (checkpoints / f'{day}_{source}.json').write_text(json.dumps(dict(status='complete', verified=True)))
            state = base / '.etl_02_state.json'
            state.write_text(json.dumps(records))
            with patch.object(resume, 'ETL', root):
                self.assertEqual(len(resume.check_final(base, day)), 2)
                local_final = base / 'stage/final_clean'
                external_final = root / 'nas_final_clean'
                local_final.rename(external_final)
                jobs = resume.check_final(base, day, external_final)
                self.assertTrue(all(Path(job['final_clean_file']).is_relative_to(external_final) for job in jobs))
                external_final.rename(local_final)
                records['stream_2026_10_18']['rows'] = 3
                state.write_text(json.dumps(records))
                with self.assertRaisesRegex(RuntimeError, 'final-clean'):
                    resume.check_final(base, day)
                records['stream_2026_10_18']['rows'] = 2
                state.write_text(json.dumps(records))
                (checkpoints / f'{day}_stream.json').write_text(json.dumps(dict(status='complete', verified=False)))
                with self.assertRaisesRegex(RuntimeError, 'Download'):
                    resume.check_final(base, day)


if __name__ == '__main__':
    unittest.main()

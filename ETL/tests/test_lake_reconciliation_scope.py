import pyarrow as pa
import pyarrow.parquet as pq

from ETL.src.orchestrator.run_pipeline import _lake_rows_for_source


def test_reconcile_counts_spillover_and_legacy_but_not_temp(tmp_path):
    fixtures = {
        'source=fast/year=2026/month=11/day=02/part_fast_2026_11_02_0.parquet': 3,
        'source=fast/year=2026/month=11/day=03/part_fast_2026_11_02_0.parquet': 2,
        'year=2026/month=11/day=02/src_fast_2026_11_02_0.parquet': 1,
        'Temp/work/part_fast_2026_11_02_0.parquet': 99,
        'Temp/lake/source=fast/year=2026/month=11/day=02/part_fast_2026_11_02_0.parquet': 99,
    }
    for name, count in fixtures.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.table({'value': range(count)}), path)
    assert _lake_rows_for_source(tmp_path, 'fast_2026_11_02', 'fast') == 6

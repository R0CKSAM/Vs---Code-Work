import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/tools'))
from refresh_overview_backlog_20261014 import merge_repaired_rows, reusable_dates


def test_preserves_newer_live_date():
    live = [{'source': 'fast', 'date': '13', 'rows': '100'},
            {'source': 'fast', 'date': '11', 'rows': '4'}]
    cached = [{'source': 'fast', 'date': '09', 'rows': '6'},
              {'source': 'fast', 'date': '11', 'rows': '8'},
              {'source': 'fast', 'date': '13', 'rows': '1'}]
    result = merge_repaired_rows(live, cached, ['09', '11'], ('source', 'date'), 'date')
    assert result == [live[0], cached[0], cached[1]]


def test_rejects_incomplete_cache():
    with pytest.raises(ValueError, match='every requested'):
        merge_repaired_rows([], [], ['09'], ('source', 'date'), 'date')


def test_rejects_duplicate_keys():
    row = {'source': 'fast', 'date': '09', 'rows': '1'}
    with pytest.raises(ValueError, match='Duplicate'):
        merge_repaired_rows([], [row, row], ['09'], ('source', 'date'), 'date')


def test_late_arrivals_invalidate_only_changed_day():
    cached = [{'source': source, 'date': day, 'rows': '100'}
              for source in ('fast', 'stream') for day in ('09', '12')]
    truth = {(r['source'], r['date']): 100 for r in cached}
    truth[('fast', '12')] += 8
    assert reusable_dates(cached, ['09', '12'], truth) == ['09']


def test_no_replacement_preserves_current_rows():
    live = [{'source': 'fast', 'date': '13', 'rows': '100'}]
    assert merge_repaired_rows(live, [], [], ('source', 'date'), 'date') == live


def test_daily_overview_can_include_older_gaps_and_late_arrivals():
    import pandas as pd
    from repair_overview_true_source import selected_repair_dates
    mismatch = pd.DataFrame([{'date': '2026-10-09', 'rows_true': 100},
                             {'date': '2026-10-12', 'rows_true': 108},
                             {'date': '2026-10-08', 'rows_true': 0}])
    assert selected_repair_dates('2026-10-13', mismatch) == ['2026-10-13']
    assert selected_repair_dates('2026-10-13', mismatch, True) == ['2026-10-09', '2026-10-12', '2026-10-13']

"""Regressions for doubled hours and invalid unique-IP aggregation."""
from pathlib import Path
import re
import subprocess
import importlib.util
import pandas as pd

TEMPLATE = Path(__file__).parents[1] / 'src/dashboards/audienceOpsDashboard/template.html'


def test_browser_aggregation_rules():
    text = TEMPLATE.read_text(encoding='utf-8')
    names = ['n', 'fmtInt', 'groupSum', 'topBy', 'geoIpGroups', 'geoIpValue', 'geoIpText']
    functions = []
    for name in names:
        match = re.search(r'^function '+name+r'\(.*?(?=^function |\Z)', text, re.M | re.S)
        assert match, name
        functions.append(match.group(0))
    js = '\n'.join(functions) + '''
const assert = require('node:assert/strict');
const rows=[{country:'BD',raw_watch_hours:10,raw_ts_rows:6000,approx_unique_ips:90,exact_unique_ips:70},
{country:'BD',raw_watch_hours:2,raw_ts_rows:1200,approx_unique_ips:40,exact_unique_ips:35}];
const result=topBy(rows,r=>r.country,'raw_watch_hours',15);
assert.equal(result[0].raw_watch_hours,12);
assert.equal(result[0].raw_ts_rows,7200);
assert.equal(geoIpValue([rows[0]]).value,70);
assert.equal(geoIpValue(rows).value,null);
assert.equal(geoIpValue([{exact_unique_ips:null,approx_unique_ips:90}]).label,'90 (approx.)');
assert.equal(geoIpValue([{exact_unique_ips:0,approx_unique_ips:90}]).value,0);
assert.equal(geoIpText(rows,r=>r.country,'BD'),'Unavailable: overlapping groups');
'''
    subprocess.run(['node', '-e', js], check=True, capture_output=True, text=True)


def test_historical_missing_exact_counts_survive_profile_merge():
    path = TEMPLATE.parents[2] / 'profile/merge_watch_profile_delta.py'
    spec = importlib.util.spec_from_file_location('merge_profile_geo_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    old = pd.DataFrame([{'source':'stream','log_date':'2026-11-10','approx_unique_ips':90}])
    new = pd.DataFrame([{'source':'stream','log_date':'2026-11-11','approx_unique_ips':90,'exact_unique_ips':70}])
    merged = module.normalize_for_parquet(module.merge_date_rows(old,new,{'2026-11-11'}))
    assert pd.isna(merged.iloc[0]['exact_unique_ips'])
    assert merged.iloc[1]['exact_unique_ips'] == 70


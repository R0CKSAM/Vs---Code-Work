"""Refresh geography and rendering while preserving the published dashboard's other data."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import importlib.util,json

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('audience_geo_refresh',ROOT/'src/dashboards/audienceOpsDashboard/generate_audience_ops.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
published=ROOT/'output/audience_ops/veto_audience_operations.html'
with published.open(encoding='utf-8') as f:
    for line in f:
        if line.startswith('const D = '):
            data=json.loads(line[len('const D = '):].strip().rstrip(';'));break
    else:raise ValueError('Missing dashboard payload')
watch=ROOT/'output/watch_hours/daily_tables'
for name,builder in [('geo_daily',mod.build_geo),('channel_geo_daily',mod.build_channel_geo)]:
    frame=builder(watch)
    frame=frame[(frame.log_date>=data['meta']['min_date'])&(frame.log_date<=data['meta']['max_date'])]
    data['data'][name+'_schema']=mod.compact_schema(frame)
    data['data'][name]=mod.compact_records(frame)
    assert len(data['data'][name])==len(frame)
    assert frame.log_date.max()=='2026-11-11'
    print(name,len(frame),'rows; latest',frame.log_date.max(),flush=True)
data['meta']['geography_repaired_at']=datetime.now(ZoneInfo('Asia/Kolkata')).isoformat()
chartjs=(ROOT/'output/cache/chartjs/chart.umd.min.js').read_text(encoding='utf-8')
html=mod.render_template(mod.HERE/'template.html',CHARTJS_TAG=mod.chartjs_script(chartjs),DATA_BLOB=mod.json_blob(data))
staged=ROOT/'output/audience_ops/veto_audience_operations.geo_repaired.html'
staged.write_text(html,encoding='utf-8')
print('Staged',staged,flush=True)

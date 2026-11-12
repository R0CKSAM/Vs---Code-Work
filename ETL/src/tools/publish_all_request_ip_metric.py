"""Merge the initial exact membership backfill and stage the dashboard card."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import argparse,importlib.util,json,shutil
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser()
parser.add_argument('--geography',action='store_true')
args=parser.parse_args()
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module
merge=load('allip_merge',ROOT/'src/profile/merge_watch_profile_delta.py')
gen=load('allip_gen',ROOT/'src/dashboards/audienceOpsDashboard/generate_audience_ops.py')
target=ROOT/'output/watch_hours/daily_tables/channel_ip_all_requests_daily.parquet'
batch='all_request_geo_20261111' if args.geography else 'all_request_ips_20261111'
fresh=pd.read_parquet(ROOT/'output/temp'/batch/'daily_tables'/target.name)
assert set(fresh.source)=={'fast','stream'}
assert set(fresh.log_date)=={'2026-11-11'}
assert not fresh.duplicated().any()
assert fresh.cliIP.dropna().str.strip().eq(fresh.cliIP.dropna()).all()
assert not fresh.cliIP.dropna().eq('').any()
backup=ROOT/'output/audience_ops/history'/('all_request_geo_20261112' if args.geography else 'all_request_ips_20261112')
backup.mkdir(parents=True,exist_ok=True)
old=pd.read_parquet(target) if target.exists() else pd.DataFrame()
if args.geography:
    assert fresh.geo_membership_version.eq(1).all()
    keys=['source','log_date','channel_name','cliIP']
    before=old.loc[old.log_date=='2026-11-11',keys].fillna('').drop_duplicates().sort_values(keys).reset_index(drop=True)
    after=fresh[keys].fillna('').drop_duplicates().sort_values(keys).reset_index(drop=True)
    assert before.equals(after),'Adding geography must preserve the full original IP membership'
    # Independent reconciliation with the earlier country-filtered raw-lake export.
    bd_export=pd.read_csv(ROOT/'output/exports/stream_BD_2026-11-11/all_request_activity.csv',dtype={'cliIP':'string'})
    for channel in [None,'Weightlifting (dreamboat-ch01)']:
        actual=fresh[(fresh.source=='stream')&(fresh.country=='BD')]
        prior=bd_export
        if channel:
            actual=actual[actual.channel_name==channel];prior=prior[prior.channel==channel]
        assert actual.cliIP.nunique()==prior.cliIP.str.strip().replace('',pd.NA).nunique()
if target.exists() and not (backup/target.name).exists():shutil.copy2(target,backup/target.name)
combined=merge.merge_date_rows(old,fresh,{'2026-11-11'})
tmp=target.with_suffix('.staged.parquet');combined.to_parquet(tmp,index=False,compression='zstd');tmp.replace(target)
summary={'source_exact_ips':fresh.groupby('source').cliIP.nunique().to_dict(),'membership_rows':len(fresh),'channel_exact_ips':[]}
counts=fresh.groupby(['source','channel_name']).cliIP.nunique().reset_index(name='exact_ips')
summary['channel_exact_ips']=counts.sort_values('exact_ips',ascending=False).to_dict('records')
(backup/'validation.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
published=ROOT/'output/audience_ops/veto_audience_operations.html'
with published.open(encoding='utf-8') as f:
    for line in f:
        if line.startswith('const D = '):data=json.loads(line[len('const D = '):].strip().rstrip(';'));break
    else:raise ValueError('Missing payload')
data['data']['all_request_ip_membership']=gen.build_all_request_ip_membership(target.parent,data['meta']['max_date'])
if args.geography:
    data['data']['all_request_geo_membership']=gen.build_all_request_ip_membership(target.parent,data['meta']['max_date'],geography=True)
data['meta']['all_request_ip_metric_updated_at']=datetime.now(ZoneInfo('Asia/Kolkata')).isoformat()
chartjs=(ROOT/'output/cache/chartjs/chart.umd.min.js').read_text(encoding='utf-8')
html=gen.render_template(gen.HERE/'template.html',CHARTJS_TAG=gen.chartjs_script(chartjs),DATA_BLOB=gen.json_blob(data))
staged=ROOT/'output/audience_ops'/('veto_audience_operations.regional_ips.html' if args.geography else 'veto_audience_operations.all_ips.html')
staged.write_text(html,encoding='utf-8')
print(json.dumps({'staged':str(staged),'source_exact_ips':summary['source_exact_ips'],'membership_rows':len(fresh),'groups':len(data['data']['all_request_ip_membership']['groups'])},indent=2),flush=True)

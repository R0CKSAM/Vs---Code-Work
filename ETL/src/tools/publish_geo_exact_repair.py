"""Validate and merge the isolated 11-Nov geography repair, preserving history."""
from pathlib import Path
import importlib.util
import json
import shutil
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('geo_merge',ROOT/'src/profile/merge_watch_profile_delta.py')
merge=importlib.util.module_from_spec(spec);spec.loader.exec_module(merge)
base=ROOT/'output/watch_hours/daily_tables'
delta=ROOT/'output/temp/geo_exact_20261111/daily_tables'
backup=ROOT/'output/audience_ops/history/geo_repair_20261112'
backup.mkdir(parents=True,exist_ok=True)
report={}
staged=[]
for name in ['geo_daily','channel_geo_daily']:
    original=pd.read_parquet(base/(name+'.parquet'))
    fresh=pd.read_parquet(delta/(name+'.parquet'))
    assert set(fresh.source)=={'fast','stream'}
    assert set(fresh.log_date.astype(str))=={'2026-11-11'}
    old_day=original[original.log_date.astype(str)=='2026-11-11']
    for metric in ['raw_ts_rows','status_200_ts_rows']:
        assert original.groupby('source')[metric].sum().notna().all()
        assert old_day.groupby('source')[metric].sum().to_dict()==fresh.groupby('source')[metric].sum().to_dict()
    bd=fresh[(fresh.source=='stream')&(fresh.country=='BD')]
    assert bd.raw_ts_rows.sum()==8748415
    if name=='geo_daily':
        assert len(bd)==1 and int(bd.iloc[0].exact_unique_ips)==63496
    else:
        assert len(bd)==31
        assert int(bd[bd.channel_name=='Weightlifting (dreamboat-ch01)'].iloc[0].exact_unique_ips)==63454
    combined=merge.normalize_for_parquet(merge.merge_date_rows(original,fresh,{'2026-11-11'}))
    historical=combined[combined.log_date.astype(str)!='2026-11-11']
    assert historical.exact_unique_ips.isna().all()
    target=base/(name+'.parquet')
    if not (backup/target.name).exists():shutil.copy2(target,backup/target.name)
    tmp=base/(name+'.repair.parquet');combined.to_parquet(tmp,index=False,compression='zstd')
    staged.append((tmp,target))
    report[name]={'rows':len(combined),'rebuilt_rows':len(fresh),'BD_exact_counts':bd[['source','country','exact_unique_ips']].to_dict('records')}
for tmp,target in staged:tmp.replace(target)
(backup/'validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))

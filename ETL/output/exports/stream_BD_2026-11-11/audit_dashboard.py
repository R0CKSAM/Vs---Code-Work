import json,csv
from pathlib import Path
from collections import defaultdict
import duckdb
root=Path(__file__).resolve().parents[2]
html=root/'audience_ops/veto_audience_operations.html'
with html.open(encoding='utf-8') as f:
    for line in f:
        if line.startswith('const D = '):
            data=json.loads(line[len('const D = '):].strip().rstrip(';'));break
print('meta',data['meta'])
print('root keys',list(data))
tables=data.get('data',data.get('datasets',{}))
print('table keys',list(tables)[:25])
if not tables:
    for k,v in data.items():
        if isinstance(v,dict) and 'geo_daily' in v:tables=v;break
result={}
for name in ['geo_daily','channel_geo_daily']:
    headers=tables[name+'_schema']
    rows=[dict(zip(headers,r)) for r in tables[name]]
    selected=[r for r in rows if r.get('source')=='stream' and str(r.get('log_date'))[:10]=='2026-11-11' and r.get('country')=='BD']
    result[name]={'embedded_total_rows':len(rows),'min_date':min(str(r.get('log_date')) for r in rows),'max_date':max(str(r.get('log_date')) for r in rows),'BD_rows':len(selected),
      'sums':{k:sum(float(r.get(k) or 0) for r in selected) for k in ['raw_ts_rows','status_200_ts_rows','raw_watch_hours','status_200_watch_hours','approx_unique_ips']}}
    grouped=defaultdict(lambda:defaultdict(float))
    for r in selected:
        for k in ['raw_ts_rows','status_200_ts_rows','raw_watch_hours','status_200_watch_hours','approx_unique_ips']:grouped[r.get('channel_name','ALL')][k]+=float(r.get(k) or 0)
    result[name]['channels']=dict(grouped)
    con=duckdb.connect()
    cur=con.execute("SELECT * FROM read_parquet(?) WHERE source='stream' AND cast(log_date AS VARCHAR) LIKE '2026-11-11%' AND country='BD'",[str(root/'watch_hours/daily_tables'/f'{name}.parquet')])
    p_rows=[dict(zip([c[0] for c in cur.description],r)) for r in cur.fetchall()]
    result[name]['parquet_BD_rows']=len(p_rows)
    result[name]['parquet_sums']={k:sum(float(r.get(k) or 0) for r in p_rows) for k in ['raw_ts_rows','status_200_ts_rows','raw_watch_hours','status_200_watch_hours','approx_unique_ips']}
with (Path(__file__).parent/'channel_summary.csv').open(encoding='utf-8-sig') as f:export=list(csv.DictReader(f))
diffs=[]
for r in export:
    dashboard=result['channel_geo_daily']['channels'].get(r['channel'],{})
    delta=int(r['all_http_ts_requests'])-dashboard.get('raw_ts_rows',0)
    if delta:diffs.append({'channel':r['channel'],'export_ts':int(r['all_http_ts_requests']),'dashboard_ts':dashboard.get('raw_ts_rows',0),'delta':delta})
result['channel_ts_differences']=diffs
result['export_http200_request_hours']=sum(int(r['http200_ts_requests']) for r in export)/600
result['export_all_ts_hours']=sum(int(r['all_http_ts_requests']) for r in export)/600
(Path(__file__).parent/'dashboard_audit.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))

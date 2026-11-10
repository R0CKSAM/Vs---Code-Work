"""Cross-check columnar analysis against independent SQLite period queries."""
from pathlib import Path
from datetime import date,timedelta
import json,math,sqlite3,urllib.request,sys
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT))
from insights import geography
checks=[]
def check(name,ok):
    assert ok,name
    checks.append(name)
meta=json.loads((ROOT/'data/manifest.json').read_text());con=sqlite3.connect(ROOT/'data'/meta['database']);end=date.fromisoformat(meta['dates'][-1])
for metric,level,dimension,days,lo,hi,filters in [('hours','state','isp',1,'00:00','23:59',{}),('devices','city','os',3,'18:00','22:59',{'device_type':['mobile']}),('ips','country','title',2,'23:00','01:00',{})]:
    start=end-timedelta(days=days-1);old_end=start-timedelta(days=1);old_start=start-timedelta(days=days)
    body=dict(start=start.isoformat(),end=end.isoformat(),filters=filters,timeStart=lo,timeEnd=hi,insight_metric=metric,geo_level=level,insight_dimension=dimension)
    request=urllib.request.Request('http://127.0.0.1:8766/api/insights',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    data=json.load(urllib.request.urlopen(request,timeout=120));aggregate={'hours':'sum(hours)','devices':"count(DISTINCT nullif(device_id,'Unknown'))",'ips':"count(DISTINCT nullif(cli_ip,'Unknown'))"}[metric]
    clauses='day BETWEEN ? AND ? AND '+('clock BETWEEN ? AND ?' if lo<=hi else '(clock>=? OR clock<=?)')+(' AND device_type=?' if filters else '')
    def params(a,b):return [a.isoformat(),b.isoformat(),lo,hi]+(['mobile'] if filters else [])
    current=con.execute('SELECT '+aggregate+' FROM events WHERE '+clauses,params(start,end)).fetchone()[0] or 0
    previous=con.execute('SELECT '+aggregate+' FROM events WHERE '+clauses,params(old_start,old_end)).fetchone()[0] or 0
    check(metric+' uses columnar projection',data['backend']=='columnar')
    check(metric+' current period matches SQLite',math.isclose(current,data['summary']['current'],abs_tol=1e-6))
    check(metric+' previous period matches SQLite',math.isclose(previous,data['summary']['previous'],abs_tol=1e-6))
    con.create_function('geo',1,lambda value:geography(value,level))
    expected=dict(con.execute('SELECT geo(region),'+aggregate+' FROM events WHERE '+clauses+' GROUP BY 1',params(start,end)))
    check(metric+' regional aggregates match SQLite',all(math.isclose(expected.get(r['label'],0),r['current'],abs_tol=1e-6) for r in data['regions']))
    labels={r['label'] for r in data['region_series']}
    check(metric+' every flagged region has its own trend',all(r['label'] in labels for r in data['movers']+data['alerts']))
    check(metric+' all values finite',all(r['pct'] is None or math.isfinite(r['pct']) for r in data['regions']))
con.close();(ROOT/'audit/insights_reconcile.json').write_text(json.dumps({'passed':True,'checks':checks},indent=2));print('PASS',len(checks),'cross-backend reconciliation checks')

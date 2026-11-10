"""Deterministic fixtures for comparison, distinct counts, gaps and anomaly rules."""
from pathlib import Path
from contextlib import contextmanager
from datetime import date,timedelta
import json,sqlite3,sys,tempfile,math
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT))
import insights,server
checks=[]
def check(name,ok):
    assert ok,name
    checks.append(name)
check('Stable baseline has no alert',insights.anomaly(12,[10]*7,1) is None)
check('Large rise is flagged',insights.anomaly(40,[10]*7,1)['direction']=='Rise')
check('Large fall is flagged',insights.anomaly(2,[20]*7,1)['direction']=='Drop')
check('Insufficient history is not an anomaly',insights.anomaly(100,[10]*3,1) is None)
check('Zero baseline never invents infinity',insights.change(10,0)['pct'] is None)
check('New activity is labelled',insights.change(10,0)['change_type']=='New activity')
meta=json.loads((ROOT/'data/manifest.json').read_text())
source=sqlite3.connect(ROOT/'data'/meta['database'])
schema=source.execute("SELECT sql FROM sqlite_master WHERE name='events'").fetchone()[0];columns=[r[1] for r in source.execute('PRAGMA table_info(events)')];source.close()
with tempfile.TemporaryDirectory(prefix='smartvod_insights_') as temp:
    path=Path(temp)/'fixture.sqlite';con=sqlite3.connect(path);con.execute(schema)
    for name,col in [('idx_day','day'),('idx_device_day','device_id,day'),('idx_cli_ip','cli_ip')]:con.execute(f'CREATE INDEX {name} ON events({col})')
    def add(day,region,value,device):
        row={c:'Unknown' for c in columns};row.update(day=day,clock='12:00',title='Test title',category='Test category',video_key='key',req_host='example.test',device_id=device,cli_ip='192.0.2.1',os='TestOS',isp='TestISP',device_type='mobile',region=region,hours=value,delivered=value,segments=int(value*600),mapping_evidence=0,status_code='200',request_ist=day+' 12:00:00',last_request_ist=day+' 12:00:00')
        con.execute('INSERT INTO events('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')',[row[c] for c in columns])
    for i in range(1,10):
        day=f'2026-11-{i:02d}';add(day,'IN / A / City A',40 if i==9 else 10,'dev-a');add(day,'IN / B / City B',5 if i==9 else 20,'dev-b')
    add('2026-11-09','IN / New / City N',2,'dev-new');add('2026-11-09','IN / Unknown / Unknown',3,'Unknown');con.commit();con.close()
    @contextmanager
    def connection():
        c=sqlite3.connect(path);c.row_factory=sqlite3.Row
        try:yield c
        finally:c.close()
    body=dict(start='2026-11-09',end='2026-11-09',filters={},timeStart='00:00',timeEnd='23:59')
    def analyze(**changes):return insights.analyze({**body,**changes},connection,server.where)
    result=analyze();check('Complete comparison available',result['comparison_available'])
    check('Current total correct',result['summary']['current']==50)
    check('Previous total correct',result['summary']['previous']==30)
    check('Absolute change correct',result['summary']['delta']==20)
    check('Percentage correct',math.isclose(result['summary']['pct'],200/3))
    regions={r['label']:r for r in result['regions']}
    check('Region A rise correct',regions['IN / A']['delta']==30 and regions['IN / A']['pct']==300)
    check('Region B decline correct',regions['IN / B']['delta']==-15 and regions['IN / B']['pct']==-75)
    check('New region percentage unavailable',regions['IN / New']['pct'] is None)
    check('Unknown geography excluded from movement headlines',not any(r['unknown'] for r in result['movers']))
    check('Seven-day baseline sees unusual A rise',any(r['label']=='IN / A' and r['direction']=='Rise' for r in result['alerts']))
    check('Unknown geography percentage correct',result['quality']['unknown_geo_pct']==6)
    devices=analyze(insight_metric='devices');check('Distinct device current correct',devices['summary']['current']==3)
    check('Distinct device baseline correct',devices['summary']['previous']==2)
    period=analyze(start='2026-11-07',insight_metric='devices')
    check('Period distinct IDs are not sum of daily counts',period['summary']['current']==3 and period['summary']['previous']==2)
    ips=analyze(insight_metric='ips');check('Shared IP counted once',ips['summary']['current']==1)
    filtered=analyze(filters={'device_type':['desktop']});check('Zero matches retain source coverage',filtered['comparison_available'] and filtered['summary']['current']==0)
    clock=analyze(timeStart='00:00',timeEnd='01:00');check('Time window applies to both periods',clock['summary']['current']==0 and clock['summary']['previous']==0)
    country=analyze(geo_level='country');check('Country grouping correct',len(country['regions'])==1 and country['regions'][0]['label']=='IN')
    check('Leaderboard shares use all hours',math.isclose(sum(r['share'] for r in result['leaders']),94))
    check('High activity is flagged for review',result['leaders'][0]['high_activity'])
    result['summary']['current']=999;check('Cached results cannot be mutated by callers',analyze()['summary']['current']==50)
    con=sqlite3.connect(path);con.execute("DELETE FROM events WHERE day='2026-11-08'");con.commit();con.close();insights.CACHE.clear()
    missing=analyze();check('Missing baseline is not zero',not missing['comparison_available'] and missing['summary']['previous'] is None)
    check('Missing comparisons have no fabricated mover claims',not missing['movers'])
    check('Missing region baseline is unavailable',all(r['previous'] is None and r['delta'] is None for r in missing['regions']))
    point=next(p for s in missing['region_series'] if s['label']=='IN / A' for p in s['points'] if p['day']=='2026-11-08')
    check('Missing source date remains a gap',point['value'] is None)
    partial=analyze(start='2026-11-08');check('Partial current period blocks comparison',not partial['comparison_available'] and not partial['period']['complete'])
    absent=analyze(start='2026-12-01',end='2026-12-01');check('Absent current data is unavailable, not zero viewing',absent['summary']['current'] is None and not absent['anomaly_available'])
    for options in [dict(insight_metric='people'),dict(geo_level='wrong'),dict(insight_dimension='device_id'),dict(viewer_basis='title'),dict(start='2020-01-01')]:
        try:analyze(**options);valid=False
        except ValueError:valid=True
        check('Reject invalid controls '+str(options),valid)
(ROOT/'audit/insights_engine.json').write_text(json.dumps({'passed':True,'checks':checks},indent=2))
print('PASS',len(checks),'insights engine checks')

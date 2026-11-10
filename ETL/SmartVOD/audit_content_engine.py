"""Business decision rules, asset identity and engagement numerator fixtures."""
from pathlib import Path
from contextlib import contextmanager
import json,sqlite3,sys,tempfile,math
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT))
import content_insights,server
checks=[]
def check(name,ok):
    assert ok,name
    checks.append(name)
meta=json.loads((ROOT/'data/manifest.json').read_text());source=sqlite3.connect(ROOT/'data'/meta['database'])
schema=source.execute("SELECT sql FROM sqlite_master WHERE name='events'").fetchone()[0];columns=[r[1] for r in source.execute('PRAGMA table_info(events)')];source.close()
with tempfile.TemporaryDirectory(prefix='content_decision_') as temp:
    path=Path(temp)/'fixture.sqlite';con=sqlite3.connect(path);con.execute(schema)
    for name,col in [('idx_day','day'),('idx_device_day','device_id,day'),('idx_cli_ip','cli_ip')]:con.execute(f'CREATE INDEX {name} ON events({col})')
    def add(day,host,key,hours,ids=1,quality='Consistent log title',delivered=1,missing=False):
        for i in range(ids):
            row={c:'Unknown' for c in columns};row.update(day=day,clock='12:00',req_host=host,video_key=key,title=host+' '+key,raw_title=key+(' old SEO label' if day<'2026-11-08' else ' new SEO label'),request_ist=day+' 12:00:00',title_status=quality,device_id='Unknown' if missing else key+'-'+str(i),cli_ip='192.0.2.1',region='IN / Test / City',os='Android',isp='Example ISP',device_type='mobile',hours=hours/ids,delivered=hours/ids*delivered,segments=int(hours/ids*600),mapping_evidence=0)
            con.execute('INSERT INTO events('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')',[row[c] for c in columns])
    for d in ['2026-11-06','2026-11-07']:
        add(d,'host-a','shared',20,60);add(d,'host-b','shared',10,2);add(d,'host-a','decline',20,50);add(d,'host-a','disappeared',10,3);add(d,'host-a','conflict',20,60,quality='Conflicting log titles')
    for d in ['2026-11-08','2026-11-09']:
        add(d,'host-a','shared',40,60);add(d,'host-b','shared',10,2);add(d,'host-a','decline',5,50);add(d,'host-a','conflict',60,60,quality='Conflicting log titles');add(d,'host-a','missing-id',10,missing=True);add(d,'host-a','delivery',10,2,delivered=.8);add(d,'host-a','new',2,50);add(d,'host-a','parallel',36,1);add(d,'host-a','verified',1,1,quality='Verified override')
    con.commit();con.close()
    @contextmanager
    def connection():
        c=sqlite3.connect(path);c.row_factory=sqlite3.Row
        try:yield c
        finally:c.close()
    body=dict(start='2026-11-08',end='2026-11-09',filters={},timeStart='00:00',timeEnd='23:59')
    def analyze(**changes):return content_insights.analyze_content({**body,**changes},connection,server.where)
    d=analyze();assets={(r['host'],r['video_key']):r for r in d['assets']};a=assets['host-a','shared'];b=assets['host-b','shared']
    check('Reused key is two separate assets',('host-a','shared') in assets and ('host-b','shared') in assets)
    check('Host A hours stay separate',math.isclose(a['hours'],80,abs_tol=1e-8))
    check('Host B hours stay separate',math.isclose(b['hours'],20,abs_tol=1e-8))
    check('Period reach is distinct, not sum of days',a['devices']==60)
    check('Average uses only known-ID hours',math.isclose(a['avg_device_minutes'],80,abs_tol=1e-8))
    check('Repeated IDs mean two distinct dates',a['repeat_ids']==60 and a['repeat_id_pct']==100)
    check('Growth delta uses same asset in prior period',math.isclose(a['delta_hours'],40,abs_tol=1e-8))
    check('Clean materially growing asset can be a test candidate',a['action']=='Test additional promotion')
    check('SEO title changes do not block promotional recommendations',assets['host-a','conflict']['action']=='Test additional promotion')
    check('Latest observed title is displayed',assets['host-a','conflict']['title']=='conflict new SEO label')
    check('Legacy conflict status is normal title history',assets['host-a','conflict']['title_status']=='Title history / SEO aliases')
    check('Verified title override remains authoritative',assets['host-a','verified']['title']=='host-a verified')
    check('Verified title status is preserved',assets['host-a','verified']['title_status']=='Verified override')
    check('Missing IDs do not become low audience demand',assets['host-a','missing-id']['action']=='Review identity coverage')
    check('Missing-ID engagement is unavailable',assets['host-a','missing-id']['avg_device_minutes'] is None)
    check('Poor delivery is investigated first',assets['host-a','delivery']['action']=='Investigate delivery')
    check('Parallel/retry activity is a review flag',assets['host-a','parallel']['action']=='Review request activity')
    check('New observation is not labelled new release',assets['host-a','new']['action']=='Monitor newly observed demand')
    check('Zero prior hours have no infinite percentage',assets['host-a','new']['pct_hours'] is None)
    check('A decline is not an automatic removal instruction',assets['host-a','decline']['action']=='Investigate demand decline')
    check('Disappeared asset retained for review',any(r['video_key']=='disappeared' and r['hours']==0 for r in d['disappeared']))
    focus=analyze(content_host='host-b',content_key='shared')
    check('Observed title history retains old and new SEO labels',len(focus['focus']['title_history'])==2)
    check('Asset detail respects the host',focus['focus']['asset']['host']=='host-b' and math.isclose(sum(p['value'] or 0 for p in focus['focus']['daily'] if p['day']>='2026-11-08'),20,abs_tol=1e-8))
    one=analyze(start='2026-11-09');check('One day does not claim repeat-day activity',all(r['repeat_ids'] is None for r in one['assets']))
    empty=analyze(filters={'video_key':['none']});check('No selected activity has no invented candidates',not empty['assets'] and not empty['opportunities'])
    d['assets'][0]['hours']=999;check('Cached decisions cannot be mutated',analyze()['assets'][0]['hours']!=999)
    c=sqlite3.connect(path);c.execute("DELETE FROM events WHERE day='2026-11-07'");c.commit();c.close();content_insights.CACHE.clear()
    missing=analyze();check('Missing baseline blocks growth claims',not missing['comparison_available'] and all(r['previous_hours'] is None for r in missing['assets']))
    check('Missing baseline blocks promotion qualification',not missing['opportunities'])
    wrong=analyze(content_host='host-z',content_key='shared');check('Unknown focus is not substituted',wrong['focus'] is None)
    for options in [dict(content_host='host-a'),dict(geo_level='bad'),dict(start='2020-01-01')]:
        try:analyze(**options);valid=False
        except ValueError:valid=True
        check('Invalid content scope rejected '+str(options),valid)
(ROOT/'audit/content_engine.json').write_text(json.dumps({'passed':True,'checks':checks},indent=2));print('PASS',len(checks),'content decision engine checks')

"""Check additive category allocation, stable asset identity and date/filter rules."""
from pathlib import Path
from contextlib import contextmanager
from datetime import date,timedelta
import json,sqlite3,tempfile,math
import category_insights as engine
import server

checks=[]
def check(name,ok):
    assert ok,name
    checks.append(name)

with tempfile.TemporaryDirectory(prefix='smartvod_categories_') as tmp:
    path=Path(tmp)/'fixture.sqlite';c=sqlite3.connect(path)
    c.execute('CREATE TABLE events(day TEXT,clock TEXT,category TEXT,hours REAL,delivered REAL,segments INT,req_host TEXT,video_key TEXT,title TEXT,raw_title TEXT,title_status TEXT,request_ist TEXT,device_id TEXT,cli_ip TEXT)')
    for name,field in [('idx_day','day'),('idx_device_day','device_id,day'),('idx_cli_ip','cli_ip')]:c.execute(f'CREATE INDEX {name} ON events({field})')
    for i in range(14):
        day=(date(2026,10,27)+timedelta(days=i)).isoformat();new=i>=7
        rows=[('sports',2,'a','key','Old name' if not new else 'Latest | SEO 100%','12:00'),(' Sports ',1 if new else 0,'a','key','Old name' if not new else 'Latest | SEO 100%','12:01'),('top_banner-1',3,'a','key','Latest | SEO 100%','20:00'),('kids',1,'b','key','Latest | SEO 100%','12:00'),('Unknown',1,'a','Unknown','Unknown','12:00')]
        if i==7:rows[0]=('sports',2,'a','key','Old SEO name','12:00')
        if not new:rows.append(('previous_only',2,'a','gone','Gone title','12:00'))
        for cat,h,host,key,title,clock in rows:c.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(day,clock,cat,h,h,int(h*600),host,key,title,title,'Consistent log title',day+' '+clock+':00','d1','192.0.2.1'))
    c.commit();c.close()
    @contextmanager
    def connection():
        c=sqlite3.connect(path);c.row_factory=sqlite3.Row
        try:yield c
        finally:c.close()
    body=dict(start='2026-11-03',end='2026-11-09',filters={},timeStart='00:00',timeEnd='23:59')
    def analyze(**updates):return engine.analyze_categories({**body,**updates},connection,server.where)
    d=analyze();cats={r['category_key']:r for r in d['categories']};members=d['memberships']
    check('Complete equal calendar baseline',d['comparison_available'])
    check('Category allocations reconcile to total',math.isclose(sum(r['hours'] for r in cats.values()),56))
    check('Case and whitespace aliases merge',cats['sports']['hours']==21 and len([r for r in cats if r=='sports'])==1)
    check('Baseline uses same category normalization',cats['sports']['previous']==14 and cats['sports']['delta']==7)
    check('No title-based genre inference',cats['top_banner-1']['hours']==21 and cats['kids']['hours']==7)
    check('Daily series adds to category total',all(math.isclose(sum(p['value'] for p in s['points']),cats[s['key']]['hours']) for s in d['series']))
    check('Disappeared category remains a real zero line',all(p['value']==0 for p in next(s for s in d['series'] if s['key']=='previous_only')['points']))
    check('Asset in two categories counted once for multi-category metric',d['multi_category_assets']==1)
    a=[r for r in members if r['host']=='a' and r['video_key']=='key']
    check('Same asset has two memberships',len(a)==2)
    check('Full asset hours not copied into each category',all(r['hours']==21 and r['asset_hours']==42 for r in a))
    check('Membership shares total 100 percent',sum(r['asset_category_share_pct'] for r in a)==100)
    check('Same title and key on other host stays separate',next(r for r in members if r['host']=='b')['asset_hours']==7)
    check('Latest SEO label retains internal pipe',all(r['title']=='Latest | SEO 100%' for r in a))
    aliases=analyze(category_title_search='Old SEO name');check('Earlier observed SEO alias finds the same unsplit asset',len(aliases['memberships'])==2 and all(r['host']=='a' and r['video_key']=='key' and r['title']=='Latest | SEO 100%' for r in aliases['memberships']))
    check('Missing key is unidentified bucket',not next(r for r in members if r['video_key']=='Unknown')['known_asset'])
    focus=analyze(category_focus='sports');check('Local category changes title list only',len(focus['memberships'])==1 and focus['summary']['current']==56 and focus['memberships'][0]['asset_hours']==42)
    asset=analyze(category_focus='sports',category_asset_host='a',category_asset_key='key');check('Asset drilldown shows all scoped categories despite local category focus',len(asset['asset_focus'])==2 and sum(r['hours'] for r in asset['asset_focus'])==42)
    filtered=analyze(filters={'category':['sports',' Sports ']});check('Master category filter changes attribution scope',filtered['summary']['current']==21 and filtered['memberships'][0]['asset_hours']==21 and filtered['memberships'][0]['category_count']==1)
    time=analyze(timeStart='19:00',timeEnd='21:00');check('IST time filters apply',time['summary']['current']==21 and time['categories'][0]['category_key']=='top_banner-1')
    search=analyze(category_title_search='%');check('Search treats percent literally',all('100%' in r['title'] for r in search['memberships']))
    check('Unmatched search returns no invented membership',analyze(category_title_search='not-a-real-title')['membership_count']==0)
    check('High page safely clamps',analyze(category_page=999)['page']==0)
    unavailable=analyze(start='2026-10-27',end='2026-11-09');check('Incomplete prior range does not invent change',not unavailable['comparison_available'] and all(r['delta'] is None for r in unavailable['categories']))
    for updates in [dict(category_page=-1),dict(category_title_search=[]),dict(category_asset_host='a'),dict(category_page=True)]:
        try:analyze(**updates);raise AssertionError('Invalid input accepted')
        except ValueError:checks.append('Invalid input rejected: '+str(updates))
    full=engine.analyze_categories(body,connection,server.where,export=True);check('Export membership scope matches visible all-category set',len(full['memberships'])==full['membership_count'])
print(json.dumps({'passed':len(checks),'checks':checks}))

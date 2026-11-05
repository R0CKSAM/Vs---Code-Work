"""Audit the seven SmartVOD upgrades using real data and browser workflows."""
import csv,io,itertools,json,math,sqlite3
from pathlib import Path
from urllib.request import Request,urlopen
from playwright.sync_api import sync_playwright
from prepare_v2 import identity
from server import FIELDS
ROOT=Path(__file__).resolve().parent;BASE='http://127.0.0.1:8766'
B=dict(start='2026-11-04',end='2026-11-04',timeStart='00:00',timeEnd='23:59',filters={})
report={'checks':[],'errors':[]}
def check(name,condition):
    assert condition,name
    report['checks'].append(name)
def api(path,body):
    with urlopen(Request(BASE+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'}),timeout=90) as r:return r.read()
def query(b):return json.loads(api('/api/query',b))
meta=json.load(urlopen(BASE+'/api/meta'));con=sqlite3.connect(ROOT/'data'/meta['database']);con.row_factory=sqlite3.Row
check('30 historical dates published',len(meta['dates'])>=30 and meta['dates'][0]=='2026-10-06')
with (ROOT.parent/'output/exports/vod_stream_query_events_2026-11-04.csv').open(encoding='utf-8-sig',newline='') as f:raw=list(csv.DictReader(f))
q=query(B)
check('Yesterday records unchanged',q['kpi']['records']==len(raw))
check('Yesterday hours reconcile to original CSV',math.isclose(q['kpi']['hours'],sum(float(r['request_watch_hours']) for r in raw),rel_tol=1e-9))
check('Total history records reconcile',con.execute('SELECT count(*) FROM events').fetchone()[0]==meta['records'])
check('No unresolved title join mismatches',con.execute("SELECT count(*) FROM events e JOIN titles t ON t.host=e.req_host AND t.video_key=e.video_key WHERE e.title!=t.title OR e.title_status!=t.status").fetchone()[0]==0)
check('Conflicting raw titles flagged',con.execute("SELECT count(*) FROM titles WHERE variants>1 AND status NOT IN ('Conflicting log titles','Verified override')").fetchone()[0]==0)
check('No unsupported verified title labels',con.execute("SELECT count(*) FROM titles WHERE status='Verified override'").fetchone()[0]==0)
sample={'device_id':'d','identity_source':'segment_query','query_string':'device_id=d'}
check('Direct Device ID requires direct matching evidence',identity(sample)=='Direct Device ID' and identity({**sample,'query_string':'session_id=s'})=='Unverified Device ID')
check('Inferred identity is not promoted to direct',identity({**sample,'identity_source':'same_cli_manifest'})=='Manifest-inferred Device ID')
check('Missing device evidence stays missing',identity({**sample,'device_id':''})=='Missing Device ID')
for confidence in meta['identity_confidence']:
    count=con.execute('SELECT count(*) FROM events WHERE day=? AND identity_confidence=?',[B['start'],confidence]).fetchone()[0]
    check('Confidence filter '+confidence,query({**B,'filters':{'identity_confidence':[confidence]}})['kpi']['records']==count)
for field in FIELDS:
    expected=[dict(r) for r in con.execute(f'SELECT {field} value,sum(segments) segments,sum(hours) hours FROM events WHERE day=? GROUP BY 1',[B['start']])]
    for sort in ['segments','hours','alpha_asc','alpha_desc']:
        opts=json.loads(api('/api/facet',{**B,'field':field,'sort':sort,'search':''}))['options']
        if sort in ('segments','hours'):ranked=sorted(expected,key=lambda r:(r[sort],r['value']),reverse=True)
        else:ranked=sorted(expected,key=lambda r:(r['value'].lower(),r['value']),reverse=sort=='alpha_desc')
        check(field+' sorting '+sort,[o['value'] for o in opts]==[o['value'] for o in ranked[:100]])
    print('Sort checks:',field,flush=True)
anchor=dict(con.execute("SELECT * FROM events WHERE day=? AND device_id!='Unknown' LIMIT 1",[B['start']]).fetchone())
for a,b in itertools.combinations(FIELDS,2):
    count=con.execute(f'SELECT count(*) FROM events WHERE day=? AND {a}=? AND {b}=?',[B['start'],anchor[a],anchor[b]]).fetchone()[0]
    check('Pair '+a+'/'+b,query({**B,'filters':{a:[anchor[a]],b:[anchor[b]]}})['kpi']['records']==count)
device=con.execute("SELECT device_id FROM events WHERE day=? AND device_id!='Unknown' GROUP BY device_id HAVING count(DISTINCT video_key)>3 ORDER BY sum(hours) DESC LIMIT 1",[B['start']]).fetchone()[0]
body={**B,'filters':{'device_id':[device]}}
journey=json.loads(api('/api/journey',body))
export=list(csv.DictReader(io.StringIO(api('/api/journey-export',body).decode('utf-8-sig'))))
check('Journey CSV contains each session',len(export)==len(journey['sessions'])>0)
check('Journey CSV watch minutes reconcile',math.isclose(sum(float(r['watch_minutes_estimated']) for r in export),sum(s['hours']*60 for s in journey['sessions']),abs_tol=1e-4))
check('Journey CSV preserves one device and provenance',all(r['identity_basis']=='device_id' and r['identity_value']==device and r['identity_confidence'] and r['title_quality'] for r in export))
con.close()
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    context=browser.new_context(viewport={'width':1440,'height':1100},permissions=['clipboard-read','clipboard-write'])
    page=context.new_page();page.on('pageerror',lambda e:report['errors'].append(str(e)))
    page.goto(BASE);page.wait_for_function("document.getElementById('status').textContent.includes('matched records')",timeout=60000)
    check('11 filter dropdowns rendered',page.locator('.filter-trigger').count()==11)
    check('Default view is latest loaded day',page.locator('#start').input_value()==meta['dates'][-1])
    page.locator('#filter-isp').click();page.locator('#options input').first.wait_for();page.locator('#filterSort').select_option('alpha_desc')
    page.wait_for_timeout(1500)
    check('Sort control refreshes options',page.locator('#options input').count()>0)
    page.keyboard.press('Escape')
    page.locator('#filter-device_id').click();page.locator('#search').fill(device)
    page.locator('#options .option').filter(has_text=device).locator('input').check();page.locator('#done').click();page.locator('#apply').click()
    page.locator('#journeyContent').wait_for(state='visible',timeout=60000)
    page.locator('#savedName').fill('Audit view');page.locator('#saveView').click()
    check('View saved in browser', 'saved' in page.locator('#viewMessage').inner_text())
    page.locator('#reset').click();page.wait_for_function("!document.getElementById('apply').disabled")
    page.locator('#loadView').click();page.locator('#journeyContent').wait_for(state='visible',timeout=60000)
    check('Saved Device ID restored',device in page.locator('#filter-device_id').inner_text())
    page.locator('#shareView').click();page.wait_for_function("location.hash.startsWith('#view=')")
    shared=page.url;page.goto(shared);page.locator('#journeyContent').wait_for(state='visible',timeout=60000)
    check('Shareable local URL restores filter state',device in page.locator('#filter-device_id').inner_text())
    with page.expect_download() as download:page.locator('#journeyExport').click()
    check('Journey CSV downloads in browser',download.value.suggested_filename=='smartvod_viewer_journey.csv')
    page.locator('#reset').click();page.wait_for_function("!document.getElementById('apply').disabled")
    page.locator('.device-card').first.click();page.locator('#journeyContent').wait_for(state='visible',timeout=60000)
    check('Device drill-down applies one Device ID',page.locator('#filter-device_id').get_attribute('class').find('active')>=0)
    page.locator('#reset').click();page.wait_for_function("!document.getElementById('apply').disabled")
    page.screenshot(path=str(ROOT/'audit/upgrade_desktop.png'),full_page=True)
    for width in (1920,768,390,320):
        page.set_viewport_size({'width':width,'height':900});check('Upgrade no overflow '+str(width),page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
        page.locator('#filter-identity_confidence').click();page.locator('#options input').first.wait_for()
        check('Upgrade popup fits '+str(width),page.locator('#picker').evaluate('(e)=>{const r=e.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight}'))
        page.keyboard.press('Escape')
    page.screenshot(path=str(ROOT/'audit/upgrade_mobile.png'),full_page=True)
    browser.close()
check('No upgrade JavaScript errors',not report['errors'])
report['passed']=True;report['history']={'days':len(meta['dates']),'records':meta['records'],'from':meta['dates'][0],'through':meta['dates'][-1]}
(ROOT/'audit/upgrade.json').write_text(json.dumps(report,indent=2))
print('PASS',len(report['checks']),'upgrade checks',flush=True)

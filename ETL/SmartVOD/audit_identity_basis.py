import json,csv,io,math,sqlite3
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parent;BASE='http://127.0.0.1:8766'
B=dict(start='2026-11-04',end='2026-11-04',timeStart='00:00',timeEnd='23:59',filters={})
checks=[]
def check(name,ok):
    assert ok,name
    checks.append(name)
def call(path,b):return urlopen(Request(BASE+path,data=json.dumps(b).encode(),headers={'Content-Type':'application/json'})).read()
meta=json.load(urlopen(BASE+'/api/meta'));con=sqlite3.connect(ROOT/'data'/meta['database'])
for basis in ('device_id','cli_ip'):
    body={**B,'identity_basis':basis};data=json.loads(call('/api/query',body))
    expected=con.execute(f"SELECT sum(hours)*60/count(DISTINCT {basis}) FROM events WHERE day=? AND {basis}!='Unknown'",[B['start']]).fetchone()[0]
    check(basis+' average excludes unknown numerator and denominator',math.isclose(data['kpi']['average_watch_minutes'],expected,rel_tol=1e-9))
    for r in data['table'][:5]:
        value=con.execute(f"SELECT sum(hours)*60/count(DISTINCT {basis}) FROM events WHERE day=? AND video_key=? AND req_host=? AND title=? AND {basis}!='Unknown'",[B['start'],r['video_key'],r['req_host'],r['title']]).fetchone()[0]
        check(basis+' per-content average '+r['video_key'],(value is None and r['average_watch_minutes'] is None) or (value is not None and math.isclose(value,r['average_watch_minutes'],rel_tol=1e-9)))
    identifier=data['devices'][0]['identity_value'];selected={**body,'filters':{basis:[identifier]}}
    journey=json.loads(call('/api/journey',selected));total=con.execute(f'SELECT sum(hours) FROM events WHERE day=? AND {basis}=?',[B['start'],identifier]).fetchone()[0]
    check(basis+' journey scoped to selected identifier',journey['identity_value']==identifier and journey['identity_basis']==basis)
    check(basis+' journey reconciles',math.isclose(sum(s['hours'] for s in journey['sessions']),total,rel_tol=1e-9))
    export=list(csv.DictReader(io.StringIO(call('/api/journey-export',selected).decode('utf-8-sig'))))
    check(basis+' journey CSV labelled correctly',all(r['identity_basis']==basis and r['identity_value']==identifier for r in export))
    check(basis+' journey CSV totals',math.isclose(sum(float(r['watch_minutes_estimated']) for r in export),total*60,abs_tol=1e-4))
    check(basis+' multiple identifiers never blended',not json.loads(call('/api/journey',{**body,'filters':{basis:[identifier,'other']}}))['sessions'])
    check(basis+' missing identifiers never blended',not json.loads(call('/api/journey',{**body,'filters':{basis:['Unknown']}}))['sessions'])
    no= json.loads(call('/api/query',{**body,'filters':{basis:['Unknown']}}))
    check(basis+' missing-only average is N/A',no['kpi']['average_watch_minutes'] is None)
try:call('/api/query',{**B,'identity_basis':'evil'});raise AssertionError('Invalid basis accepted')
except HTTPError as e:check('Invalid basis rejected',e.code==400)
errors=[]
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True);page=browser.new_page(viewport={'width':1440,'height':1000})
    page.on('pageerror',lambda e:errors.append(str(e)));page.goto(BASE)
    page.wait_for_function("document.getElementById('status').textContent.includes('matched records')")
    page.locator('#identityBasis').select_option('cli_ip');page.locator('#apply').click()
    page.wait_for_function("document.getElementById('explorerLabel').textContent==='Client IP explorer'")
    check('IP averages labelled in browser','Client IP' in page.locator('#averageLabel').inner_text())
    page.locator('.device-card').first.click();page.locator('#journeyContent').wait_for(state='visible')
    check('IP drill-down applies IP filter','active' in page.locator('#filter-cli_ip').get_attribute('class'))
    check('IP shared-address caveat visible','multiple viewers' in page.locator('#journeyStatus').inner_text())
    page.locator('#savedName').fill('IP basis audit');page.locator('#saveView').click()
    page.locator('#identityBasis').select_option('device_id');page.locator('#loadView').click()
    page.wait_for_function("!document.getElementById('apply').disabled")
    check('Saved view restores IP basis',page.locator('#identityBasis').input_value()=='cli_ip')
    with page.expect_download() as download:page.locator('#journeyExport').click()
    check('IP journey downloads',download.value.suggested_filename.endswith('.csv'))
    page.set_viewport_size({'width':390,'height':844})
    check('Basis UI fits mobile',page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
    page.screenshot(path=str(ROOT/'audit/ip_basis_mobile.png'),full_page=True)
    browser.close()
check('No browser errors',not errors)
(ROOT/'audit/identity_basis.json').write_text(json.dumps(dict(passed=True,checks=checks),indent=2))
print('PASS',len(checks),'identity-basis checks')

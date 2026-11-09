from pathlib import Path
from urllib.request import Request,urlopen
import json,sqlite3,math,csv,io
from playwright.sync_api import sync_playwright
ROOT=Path('ETL/SmartVOD');BASE='http://127.0.0.1:8766';checks=[];errors=[]
def check(n,ok):
 assert ok,n
 checks.append(n)
def api(path,body):return json.load(urlopen(Request(BASE+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})))
meta=json.load(urlopen(BASE+'/api/meta'));day=meta['dates'][-1]
body={'start':day,'end':day,'timeStart':'00:00','timeEnd':'23:59','filters':{},'identity_basis':'device_id'}
data=api('/api/query',body)
con=sqlite3.connect(ROOT/'data'/meta['database'])
for field,label in [('device_id','device'),('cli_ip','ip')]:
 expected=con.execute(f"SELECT sum(CASE WHEN {field}!='Unknown' THEN hours*60 ELSE 0 END)/nullif(count(DISTINCT nullif({field},'Unknown')),0) FROM events WHERE day=?",[day]).fetchone()[0]
 check(label+' average reconciles with SQLite',math.isclose(expected,data['kpi']['average_'+label+'_minutes'],rel_tol=1e-10))
 unknown=api('/api/query',{**body,'filters':{field:['Unknown']}})
 check(label+' unknown-only average is N/A',unknown['kpi']['average_'+label+'_minutes'] is None)
 check(label+' explorer known identifiers only',all(r['identity_value']!='Unknown' for r in data['explorers'][field]))
 for row in data['table'][:3]:
  v=con.execute(f"SELECT sum(CASE WHEN {field}!='Unknown' THEN hours*60 ELSE 0 END)/nullif(count(DISTINCT nullif({field},'Unknown')),0) FROM events WHERE day=? AND video_key=? AND title=? AND req_host=? AND title_status=?",[day,row['video_key'],row['title'],row['req_host'],row['title_status']]).fetchone()[0]
  check(label+' per-content average '+row['video_key'],row['average_'+label+'_minutes']==v or (v is not None and row['average_'+label+'_minutes'] is not None and math.isclose(v,row['average_'+label+'_minutes'],rel_tol=1e-10)))
con.close()
print('API checks passed',flush=True)
with sync_playwright() as p:
 b=p.chromium.launch(channel='msedge',headless=True);page=b.new_page(viewport={'width':1440,'height':1000},accept_downloads=True)
 page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(BASE);page.wait_for_function("document.getElementById('status').textContent.includes('matched records')",timeout=60000)
 check('Both average views visible by default',page.locator('#averageMinutes').is_visible() and page.locator('#averageIPMinutes').is_visible())
 check('Both explorers visible by default',page.locator('#deviceExplorer').is_visible() and page.locator('#ipExplorer').is_visible())
 check('Basis selector removed',page.locator('#identityBasis').count()==0)
 check('Matched-record note only in drawer',page.locator('#advancedDrawer .drawer-body #status').count()==1 and page.locator('main #status').count()==0)
 check('Brand SVG and wordmark aligned',page.evaluate("()=>{const a=document.querySelector('.brand-mark').getBoundingClientRect(),b=document.querySelector('.brand-name').getBoundingClientRect();return Math.abs(a.y+a.height/2-b.y-b.height/2)<2}"))
 page.locator('#rangeTitle').click();page.locator('#weekDateRange').click();page.locator('#applyDateRange').click();page.wait_for_function("!document.getElementById('apply').disabled",timeout=60000)
 check('Date applies without More filters',page.evaluate("applied.start===document.getElementById('start').value&&document.getElementById('advancedToggle').getAttribute('aria-expanded')==='false'"))
 page.locator('#rangeTitle').click();page.locator('#latestDateRange').click();page.locator('#applyDateRange').click();page.wait_for_function("!document.getElementById('apply').disabled",timeout=60000)
 page.locator('#filter-title').click();page.locator('#options input').first.wait_for();page.locator('#options input').first.check()
 check('Layman title action is explicit',page.locator('#done').inner_text()=='Apply title')
 page.locator('#done').click();page.wait_for_function("!document.getElementById('apply').disabled",timeout=60000)
 check('Title applies without More filters',page.evaluate("applied.filters.title.length===1&&document.getElementById('advancedToggle').getAttribute('aria-expanded')==='false'"))
 check('Dual metrics preserve same filters',page.evaluate("async()=>{const d=await(await request('/api/query',applied)).json();return document.getElementById('averageMinutes').textContent===(d.kpi.average_device_minutes==null?'N/A':fmt(d.kpi.average_device_minutes,2))&&document.getElementById('averageIPMinutes').textContent===(d.kpi.average_ip_minutes==null?'N/A':fmt(d.kpi.average_ip_minutes,2))}"))
 page.locator('#filter-title').click();page.locator('#clearField').click();page.locator('#done').click()
 page.wait_for_function("!document.getElementById('apply').disabled",timeout=60000)
 page.locator('#deviceExplorer .device-card').first.click();page.locator('#journeyContent').wait_for(state='visible',timeout=60000)
 check('Device journey uses Device ID','Device ID:' in page.locator('#journeyStatus').text_content())
 page.locator('#ipExplorer .device-card').first.click();page.locator('#journeyContentIP').wait_for(state='visible',timeout=60000);page.locator('#journeyContent').wait_for(state='visible',timeout=60000)
 check('IP journey uses Client IP','Client IP:' in page.locator('#journeyStatusIP').text_content())
 check('Both journeys present simultaneously',page.locator('#journeyContent').is_visible() and page.locator('#journeyContentIP').is_visible())
 for suffix,basis in [('', 'device_id'),('IP','cli_ip')]:
  with page.expect_download() as dl:page.locator('#journeyExport'+suffix).click()
  rows=list(csv.DictReader(Path(dl.value.path()).read_text(encoding='utf-8-sig').splitlines()))
  check(basis+' journey export stays independent',len(rows)>0 and all(r['identity_basis']==basis for r in rows))
 page.locator('#advancedToggle').click();page.wait_for_timeout(250)
 page.locator('.drawer-body').evaluate('(e)=>e.scrollTop=e.scrollHeight')
 check('Run notes at bottom of drawer scroll',page.locator('#status').is_visible() and page.locator('.drawer-body').evaluate('(e)=>e.lastElementChild.className')=='drawer-run-info')
 with page.expect_download() as dl:page.locator('#export').click()
 header=Path(dl.value.path()).read_text(encoding='utf-8-sig').splitlines()[0]
 check('CSV includes both averages','average_device_minutes' in header and 'average_ip_minutes' in header)
 page.locator('#reset').click();page.wait_for_function("!document.getElementById('apply').disabled",timeout=60000);page.locator('#closeAdvanced').click();page.wait_for_timeout(250)
 for width in [1920,1440,1024,768,390,320]:
  page.set_viewport_size({'width':width,'height':900});page.wait_for_timeout(100)
  check(f'{width} no horizontal overflow',page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
  check(f'{width} both averages fit',page.locator('.average-card').evaluate_all('(es)=>es.every(e=>e.scrollWidth<=e.clientWidth+1)'))
  boxes=page.locator('.compact-brand,.range-field,#filters .field,#advancedToggle').evaluate_all('(es)=>es.map(e=>e.getBoundingClientRect().toJSON())')
  check(f'{width} minimal bar aligned',max(r['y']+r['height']/2 for r in boxes)-min(r['y']+r['height']/2 for r in boxes)<2)
  if width in [1440,390]:page.screenshot(path=str(ROOT/f'audit/both_audiences_{width}.png'))
 check('No JS errors',not errors);b.close()
(ROOT/'audit/both_audiences.json').write_text(json.dumps({'passed':True,'checks':checks,'errors':errors},indent=2))
print('PASS',len(checks),'checks')

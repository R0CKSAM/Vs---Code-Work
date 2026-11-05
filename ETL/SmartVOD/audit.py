"""Reproducible source-data and real-browser audit of SmartVOD."""
import csv
import io
import json
import math
import time
from pathlib import Path
from urllib.request import Request,urlopen
from playwright.sync_api import sync_playwright
import server

ROOT=Path(__file__).resolve().parent
BASE='http://127.0.0.1:8766'
body=dict(start='2026-11-04',end='2026-11-04',timeStart='00:00',timeEnd='23:59',filters={})
report={'checks':[],'browser_errors':[]}
def check(name,condition):
    assert condition,name
    report['checks'].append(name)
def post(path,data):
    with urlopen(Request(BASE+path,data=json.dumps(data).encode(),headers={'Content-Type':'application/json'})) as r:return r.read()
def query(data):return json.loads(post('/api/query',data))

source=ROOT.parent/'output/exports/vod_stream_query_events_2026-11-04.csv'
with source.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
baseline=query(body)
check('All source records imported',baseline['kpi']['records']==len(rows))
check('Watch hours reconcile to source CSV',math.isclose(baseline['kpi']['hours'],sum(float(r['request_watch_hours']) for r in rows),rel_tol=1e-10))
check('Unique device IDs reconcile',baseline['kpi']['devices']==len({r['device_id'].strip() for r in rows if r['device_id'].strip()}))
check('Unique client IPs reconcile',baseline['kpi']['ips']==len({r['cli_ip'].strip() for r in rows if r['cli_ip'].strip()}))
keys=list(dict.fromkeys(r['content_code'] for r in rows if r['content_code']))[:2]
filtered={**body,'filters':{'video_key':keys}}
expected=[r for r in rows if r['content_code'] in keys]
check('Multi-select OR matches source',query(filtered)['kpi']['records']==len(expected))
os=next(r['decoded_os'] for r in expected if r['decoded_os'] not in ('Unknown / NA','Unknown',''))
combined={**body,'filters':{'video_key':keys,'os':[os]}}
check('Cross-filter AND matches source',query(combined)['kpi']['records']==sum(r['decoded_os']==os for r in expected))
window={**body,'timeStart':'12:00','timeEnd':'12:59'}
check('Inclusive minute time window',query(window)['kpi']['records']==sum('12:00'<=r['minute_ist'][11:16]<='12:59' for r in rows))
night={**body,'timeStart':'23:00','timeEnd':'01:00'}
check('Overnight time window',query(night)['kpi']['records']==sum(r['minute_ist'][11:16]>='23:00' or r['minute_ist'][11:16]<='01:00' for r in rows))
check('No-match results are zero',query({**body,'filters':{'video_key':['not-a-real-video']}})['kpi']['records']==0)
for field in server.FIELDS:
    facet=json.loads(post('/api/facet',{**body,'field':field,'search':''}))
    check(f'Searchable facet {field}',len(facet['options'])>0)
    val=facet['options'][0]['value']
    found=json.loads(post('/api/facet',{**body,'field':field,'search':val}))
    check(f'Search returns exact {field}',any(o['value']==val for o in found['options']))
isp=json.loads(post('/api/facet',{**body,'field':'isp','search':'Jio'}))
check('Decoded ISP names searchable',any('Jio' in r['value'] for r in isp['options']))
data=post('/api/export',combined).decode('utf-8-sig')
export=list(csv.DictReader(io.StringIO(data)))
check('Filtered export hours reconcile',math.isclose(sum(float(r['watch_hours_estimated']) for r in export),query(combined)['kpi']['hours'],abs_tol=1e-7))
report['baseline']=baseline['kpi']

with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1100},device_scale_factor=1)
    page.on('pageerror',lambda error:report['browser_errors'].append(str(error)))
    page.goto(BASE)
    page.wait_for_function("document.getElementById('status').textContent.includes('matched records')")
    check('All audience dropdowns rendered',page.locator('.filter-trigger').count()==len(server.FIELDS))
    for field in server.FIELDS:
        page.locator('#filter-'+field).click()
        page.locator('#options input').first.wait_for()
        page.locator('#search').fill('zzzz_no_matching_value')
        page.locator('#options .empty').filter(has_text='No matching').wait_for()
        page.keyboard.press('Escape')
    check('All dropdown search controls work',True)
    page.locator('#filter-video_key').click()
    page.locator('#options input').first.wait_for()
    page.locator('#options input').nth(0).check()
    page.locator('#options input').nth(1).check()
    page.locator('#done').click()
    check('Dropdown retains two selections','2 selected' in page.locator('#filter-video_key').inner_text())
    with page.expect_response(lambda r:'/api/query' in r.url and r.request.method=='POST') as result:page.locator('#apply').click()
    payload=result.value.json()
    page.wait_for_function("!document.getElementById('apply').disabled")
    check('Filtered browser KPI agrees with API',page.locator('#videos').inner_text()==str(payload['kpi']['videos']))
    with page.expect_download() as download:page.locator('#export').click()
    check('CSV download works',download.value.suggested_filename.endswith('.csv'))
    page.locator('#reset').click()
    page.wait_for_function("!document.getElementById('apply').disabled")
    page.screenshot(path=str(ROOT/'audit/desktop.png'),full_page=True)
    for width,height in ((1920,1080),(768,1024),(390,844),(320,740)):
        page.set_viewport_size({'width':width,'height':height})
        check(f'No document overflow at {width}px',page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        page.locator('#filter-isp').click()
        page.locator('#options input').first.wait_for()
        check(f'Filter modal fits at {width}px',page.locator('#picker').evaluate('(e)=>{const r=e.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&r.bottom<=innerHeight}'))
        page.keyboard.press('Escape')
    page.set_viewport_size({'width':390,'height':844})
    page.screenshot(path=str(ROOT/'audit/mobile.png'),full_page=True)
    page.locator('#density').select_option('compact')
    check('Compact layout works','compact' in page.locator('body').get_attribute('class'))
    page.locator('#start').fill('2026-11-05')
    page.locator('#apply').click()
    check('Invalid date range shows error',page.locator('#error').is_visible())
    browser.close()
check('No browser JavaScript errors',not report['browser_errors'])
report['passed']=True
(ROOT/'audit/report.json').write_text(json.dumps(report,indent=2))
print('PASS',len(report['checks']),'checks',json.dumps(report['baseline']))

"""Reconcile weighted status counts with source exports and exercise the UI."""
import csv,json,sys,urllib.request
from collections import Counter
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from prepare_v2 import status_code
checks=[]
def check(name,condition):
    assert condition,name
    checks.append(name)
def query(body):
    request=urllib.request.Request('http://127.0.0.1:8766/api/query',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    return json.load(urllib.request.urlopen(request,timeout=120))
meta=json.loads((ROOT/'data/manifest.json').read_text())
check('Schema retains HTTP codes',meta['schema']==4)
for value,expected in [('200','200'),('206.0','206'),('404','404'),('599','599'),('', 'Unknown'),('garbage','Unknown'),('999','Unknown')]:
    check('Normalize '+repr(value),status_code(value)==expected)
day=meta['dates'][-1]
rows=list(csv.DictReader((ROOT.parent/'output/exports'/f'vod_stream_query_events_{day}.csv').open(encoding='utf-8-sig',newline='')))
ip=rows[0]['cli_ip'].strip() or 'Unknown'
for name,filters,lo,hi in [('All',{},'00:00','23:59'),('IP',{'cli_ip':[ip]},'00:00','23:59'),('Hour',{},'18:00','18:59'),('Empty',{'video_key':['__NO_SUCH_VIDEO__']},'00:00','23:59')]:
    expected=Counter()
    for row in rows:
        if not lo<=row['minute_ist'][11:16]<=hi:continue
        if name=='IP' and (row['cli_ip'].strip() or 'Unknown')!=ip:continue
        if name=='Empty':continue
        expected[status_code(row['status_code'])]+=int(row.get('segment_count') or 1)
    result=query(dict(start=day,end=day,filters=filters,timeStart=lo,timeEnd=hi))
    actual={r['code']:r['requests'] for r in result['delivery_statuses']}
    check(name+' source reconciliation',actual==dict(expected))
    check(name+' status sum equals segment requests',sum(actual.values())==result['kpi']['segments'])
    check(name+' available',result['delivery_status_available'])
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8766/')
    page.wait_for_function("applied!==null&&!document.getElementById('apply').disabled",timeout=120000)
    check('Real status rows visible',page.locator('.status-code').count()>0)
    check('No success hero or delivery meter',page.locator('#delivered,#deliveryBar').count()==0)
    page.evaluate("renderDeliveryStatuses({delivery_status_available:true,delivery_statuses:[{code:'101',requests:1},{code:'200',requests:10},{code:'206',requests:5},{code:'304',requests:2},{code:'404',requests:3},{code:'503',requests:4},{code:'Unknown',requests:1}]})")
    check('Every observed code displayed',page.locator('.status-code').count()==7)
    check('Code order is numeric with Unknown last',page.locator('.status-code').evaluate_all('(es)=>es.map(e=>e.dataset.code)')==['101','200','206','304','404','503','Unknown'])
    check('All codes use the same neutral styling',page.locator('.status-code td:first-child').evaluate_all('(es)=>new Set(es.map(e=>getComputedStyle(e).color+getComputedStyle(e).fontWeight+getComputedStyle(e).backgroundColor)).size===1'))
    check('Unknown is explicit',page.locator('[data-code="Unknown"]').count()==1)
    for width,height in [(1440,1000),(768,900),(390,844),(320,640)]:
        page.set_viewport_size({'width':width,'height':height})
        check(str(width)+' no horizontal overflow',page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
        check(str(width)+' status rows fit',page.locator('.delivery-table').evaluate_all('(es)=>es.every(e=>e.scrollWidth<=e.clientWidth+1)'))
    page.evaluate('renderDeliveryStatuses({delivery_status_available:true,delivery_statuses:[]})')
    check('Empty state clear','No segment requests' in page.locator('#deliveryStatuses').inner_text())
    check('No browser errors',not errors)
    browser.close()
(ROOT/'audit/delivery_status.json').write_text(json.dumps({'passed':True,'checks':checks},indent=2))
print('PASS',len(checks),'delivery status checks')

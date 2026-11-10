"""Real title aliases remain one asset; metadata history is not a quality failure."""
from pathlib import Path
import json,math,urllib.request
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parent;checks=[]
def check(name,ok):
    assert ok,name
    checks.append(name)
meta=json.loads((ROOT/'data/manifest.json').read_text());body=dict(start=meta['dates'][0],end=meta['dates'][-1],filters={},timeStart='00:00',timeEnd='23:59',content_host='veto-vod.akamaized.net',content_key='nghn1tag')
def request(path,value):
    req=urllib.request.Request('http://127.0.0.1:8766'+path,data=json.dumps(value).encode(),headers={'Content-Type':'application/json'})
    return json.load(urllib.request.urlopen(req,timeout=120))
d=request('/api/content-insights',body);asset=d['focus']['asset'];history=d['focus']['title_history']
check('Asset grouping unchanged across names',math.isclose(d['summary']['current'],meta['hours'],abs_tol=1e-5))
check('SEO history has multiple observed names',len(history)>1)
check('Latest selected request title displayed',asset['title']==history[0]['title'])
check('Historical conflict label becomes normal SEO history',asset['title_status']=='Title history / SEO aliases')
check('Renaming does not trigger label verification',asset['action']!='Verify content label')
check('Renaming does not contribute to quality failure',asset['quality_rank']<2)
check('Only missing/unverified labels remain in review hours',d['quality']['label_review_pct']<35)
facet=request('/api/facet',{**body,'field':'title_status','search':'SEO'})
check('SEO labels can be searched in status picker',any(r['value'] in {'Conflicting log titles','Title history / SEO aliases'} for r in facet['options']))
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True);page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8766/');page.wait_for_function("applied!==null&&!document.getElementById('apply').disabled",timeout=120000)
    page.locator('#insightsPage').click();page.wait_for_function("!document.getElementById('insightExport').disabled",timeout=120000)
    check('Misleading label-review headline removed','Conflicting, missing' not in page.locator('#insightContent').inner_text())
    page.locator('#rangeTitle').click();page.locator('#allDateRange').click();page.locator('#applyDateRange').click()
    page.wait_for_function("!document.getElementById('apply').disabled&&!document.getElementById('insightExport').disabled",timeout=120000)
    page.locator('.content-worklist-tools input').fill('nghn1tag')
    check('SEO names do not split one host/key into multiple rows',page.locator('.content-assets-table tbody tr').count()==2)
    page.locator('.content-assets-table [data-content-host="veto-vod.akamaized.net"][data-content-key="nghn1tag"]').click();page.wait_for_function("!document.getElementById('insightExport').disabled",timeout=120000)
    page.locator('.content-title-history summary').click()
    check('Title history is visible',page.locator('.content-title-history tbody tr').count()>1)
    check('Observation timestamps are not claimed as edit timestamps','not confirmed SEO edit timestamps' in page.locator('.content-title-history').inner_text())
    page.locator('.content-title-history').screenshot(path=str(ROOT/'audit/seo_title_history.png'))
    check('No JavaScript errors',not errors);browser.close()
(ROOT/'audit/seo_titles.json').write_text(json.dumps({'passed':True,'checks':checks},indent=2));print('PASS',len(checks),'SEO title-history checks')

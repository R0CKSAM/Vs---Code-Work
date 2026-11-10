"""Content-first workflow and real host/key reconciliation."""
from pathlib import Path
import csv,json,math,sqlite3,urllib.request
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parent;checks=[]
def check(name,ok):
    assert ok,name
    checks.append(name)
meta=json.loads((ROOT/'data/manifest.json').read_text());body=dict(start=meta['dates'][0],end=meta['dates'][-1],filters={},timeStart='00:00',timeEnd='23:59')
def api(options):
    r=urllib.request.Request('http://127.0.0.1:8766/api/content-insights',data=json.dumps(options).encode(),headers={'Content-Type':'application/json'})
    return json.load(urllib.request.urlopen(r,timeout=120))
data=api(body);check('Content total reconciles with snapshot',math.isclose(data['summary']['current'],meta['hours'],abs_tol=1e-5))
check('All assets use separate host/key pairs',len({(r['host'],r['video_key']) for r in data['assets']})==len(data['assets']))
con=sqlite3.connect(ROOT/'data'/meta['database'])
for host in ['tennis-vod.akamaized.net','veto-vod.akamaized.net']:
    result=api({**body,'content_host':host,'content_key':'nghn1tag'})
    expected=con.execute("SELECT sum(hours),sum(delivered),count(DISTINCT nullif(device_id,'Unknown')) FROM events WHERE req_host=? AND video_key=?",[host,'nghn1tag']).fetchone();row=result['focus']['asset']
    check(host+' correct asset hours',math.isclose(row['hours'],expected[0],abs_tol=1e-5))
    check(host+' correct delivered hours',math.isclose(row['delivered'],expected[1],abs_tol=1e-5))
    check(host+' correct period-distinct reach',row['devices']==expected[2])
con.close()
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True);page=browser.new_page(viewport={'width':1440,'height':1000},accept_downloads=True);errors=[];calls=[]
    page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda r:calls.append(r.url) if r.url.endswith('/api/query') else None)
    def ready():page.wait_for_function("applied!==null&&!document.getElementById('apply').disabled",timeout=120000)
    def content_ready():page.wait_for_function("!document.getElementById('insightExport').disabled",timeout=120000)
    page.goto('http://127.0.0.1:8766/');ready();page.locator('#insightsPage').click();content_ready()
    check('Content decisions is the default tab',page.locator('#insightTab-content').get_attribute('aria-selected')=='true')
    check('Audience controls do not distract content view',page.locator('.insight-controls').is_hidden())
    check('Content readiness and worklist visible',page.locator('.content-assets-table').count()==1 and page.locator('.content-method').count()==1)
    count=len(calls);page.locator('#rangeTitle').click();page.locator('#allDateRange').click();page.locator('#applyDateRange').click();ready();content_ready()
    check('Content date changes avoid dashboard workload',len(calls)==count)
    check('No missing baseline is called a measured decline','comparison unavailable' in page.locator('#insightContent').inner_text().lower())
    search=page.locator('.content-worklist-tools input');search.fill('nghn1tag')
    check('Reused key yields two rows, not one merged title',page.locator('.content-assets-table tbody tr').count()==2)
    page.locator('.content-assets-table [data-content-host="tennis-vod.akamaized.net"][data-content-key="nghn1tag"]').click();content_ready()
    check('Inspection keeps exact host/key', 'tennis-vod.akamaized.net / nghn1tag' in page.locator('.content-focus-heading').inner_text())
    check('Asset has daily trend and five audience mixes',page.locator('#contentFocus svg').count()==1 and page.locator('.content-mix').count()==5)
    page.locator('#contentFocus .panel-heading button').click();check('Content trend expands',page.locator('.insight-dialog').is_visible());page.keyboard.press('Escape')
    with page.expect_download() as dl:page.locator('#insightExport').click()
    rows=list(csv.DictReader(Path(dl.value.path()).read_text(encoding='utf-8-sig').splitlines()))
    check('CSV contains host/key identity and decision evidence',bool(rows) and {'host','video_key','reason','title_quality','known_id_hour_coverage_pct'}.issubset(rows[0]))
    check('CSV retains both hosts for reused key',len({r['host'] for r in rows if r['video_key']=='nghn1tag'})==2)
    page.locator('#insightQuestion').fill('Which content should we promote?');page.locator('#insightQuestionForm button').click()
    check('Promotion question keeps promotion-test filter',page.locator('.content-worklist-tools select').first.input_value()=='Test additional promotion')
    check('Unqualified assets are not recommended','Promotion-test scoring needs' in page.locator('#insightContent').inner_text())
    page.locator('.content-method summary').click();check('Unavailable ROI/completion inputs disclosed','cost' in page.locator('.content-method').inner_text().lower() and 'runtime' in page.locator('.content-method').inner_text().lower())
    page.locator('#insightQuestion').fill('Which regions dropped?');page.locator('#insightQuestionForm button').click();content_ready()
    page.wait_for_function("document.getElementById('insightTab-changes').getAttribute('aria-selected')==='true'",timeout=120000)
    check('Audience analysis remains available',page.locator('.insight-controls').is_visible())
    page.locator('#insightTab-content').click();content_ready();page.locator('.content-worklist-tools select').first.select_option('all');page.locator('.content-worklist-tools input').fill('')
    for width,height in [(1920,1080),(1024,900),(768,900),(390,844),(320,640)]:
        page.set_viewport_size({'width':width,'height':height});page.wait_for_timeout(150)
        check(str(width)+' content view fits',page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
        check(str(width)+' worklist scroll is contained',page.locator('.insight-table-scroll').first.evaluate('e=>e.scrollWidth>=e.clientWidth'))
        if width==390:page.screenshot(path=str(ROOT/'audit/content_mobile.png'))
    page.set_viewport_size({'width':1440,'height':1000});page.evaluate('scrollTo(0,0)');page.wait_for_timeout(1800);page.screenshot(path=str(ROOT/'audit/content_decisions.png'))
    check('No browser errors '+str(errors),not errors);browser.close()
(ROOT/'audit/content_ui.json').write_text(json.dumps({'passed':True,'checks':checks},indent=2));print('PASS',len(checks),'content workflow and reconciliation checks')

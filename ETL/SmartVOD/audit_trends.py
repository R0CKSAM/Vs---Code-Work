"""Reconcile time-series aggregates and exercise chart/loader interactions."""
import json,math,sqlite3,urllib.request
from collections import defaultdict
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parent;checks=[]
def check(name,ok):
    assert ok,name
    checks.append(name)
def request(body):
    r=urllib.request.Request('http://127.0.0.1:8766/api/query',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    return json.load(urllib.request.urlopen(r,timeout=120))
meta=json.loads((ROOT/'data/manifest.json').read_text());days=meta['dates'][-3:]
con=sqlite3.connect(ROOT/'data'/meta['database'])
for name,filters,lo,hi in [('All',{},'00:00','23:59'),('Mobile',{'device_type':['mobile']},'18:00','22:59'),('Empty',{'video_key':['__NO_SUCH_VIDEO__']},'00:00','23:59')]:
    body=dict(start=days[0],end=days[-1],filters=filters,timeStart=lo,timeEnd=hi)
    data=request(body)
    check(name+' daily hours reconcile',math.isclose(sum(r['hours'] for r in data['hourly_by_day']),data['kpi']['hours'],abs_tol=1e-7))
    check(name+' status hours reconcile',math.isclose(sum(r['hours'] for r in data['delivery_statuses']),data['kpi']['hours'],abs_tol=1e-7))
    expected=dict(con.execute('SELECT day||\'|\'||substr(clock,1,2),sum(hours) FROM events WHERE day BETWEEN ? AND ? AND clock BETWEEN ? AND ?'+(' AND device_type=?' if name=='Mobile' else ' AND video_key=?' if name=='Empty' else '')+' GROUP BY 1',[days[0],days[-1],lo,hi]+(['mobile'] if name=='Mobile' else ['__NO_SUCH_VIDEO__'] if name=='Empty' else [])))
    actual={r['day']+'|'+r['hour']:r['hours'] for r in data['hourly_by_day']}
    check(name+' day/hour matches independent SQL',actual.keys()==expected.keys() and all(math.isclose(actual[k],expected[k],abs_tol=1e-7) for k in actual))
    for field,top in data['breakdown'].items():
        totals=defaultdict(float)
        for row in data['breakdown_trends'][field]:totals[row['label']]+=row['hours']
        check(name+' '+field+' top-five trend totals',all(math.isclose(totals[r['label']],r['hours'],abs_tol=1e-7) for r in top))
con.close()
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True);page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    def ready():page.wait_for_function("applied!==null&&!document.getElementById('apply').disabled",timeout=120000);page.wait_for_timeout(200)
    page.goto('http://127.0.0.1:8766/');ready()
    check('Snapshot watch hours restored',page.locator('#snapshotHours').inner_text().endswith(' h'))
    check('Snapshot delivered hours restored',page.locator('#snapshotDelivered').inner_text().endswith(' h'))
    check('Per-code hours header present','Watch hours' in page.locator('.delivery-table thead').inner_text())
    check('Four audience trend charts visible',page.locator('.breakdown-trend svg').count()==4)
    check('One day has one comparison line',page.locator('#chart .trend-line').count()==1)
    page.evaluate('d=>{document.getElementById("start").value=d[0];document.getElementById("end").value=d[2];renderFilters();apply()}',days);ready()
    check('Three dates have three separate lines',page.locator('#chart .trend-line').count()==3)
    first=page.locator('#chart .trend-legend button').first;first.click()
    check('Legend toggle hides one day',page.locator('#chart .trend-line').count()==2)
    page.locator('#chart .trend-legend button').first.click()
    check('Legend toggle restores day',page.locator('#chart .trend-line').count()==3)
    page.locator('#chart [data-mode="continuous"]').click()
    check('Continuous chart is one timeline',page.locator('#chart .trend-line').count()==1)
    viewport=page.locator('#chart .trend-viewport')
    check('Continuous chart scrolls horizontally',viewport.evaluate('e=>e.scrollWidth>e.clientWidth'))
    viewport.evaluate('e=>e.scrollLeft=800');check('Can reach later hours and dates',viewport.evaluate('e=>e.scrollLeft')>700)
    check('Watch-hour scale stays visible while scrolling',abs(viewport.locator('.trend-y-axis').bounding_box()['x']-viewport.bounding_box()['x'])<2)
    gap_data=request(dict(start=days[0],end=days[-1],filters={},timeStart='00:00',timeEnd='23:59'))
    original=json.loads(json.dumps(gap_data));gap_data['trend_dates']=[days[0],days[-1]];gap_data['hourly_by_day']=[r for r in gap_data['hourly_by_day'] if r['day']!=days[1]]
    page.evaluate('data=>renderWatchTrends(data)',gap_data)
    check('Missing source date leaves a gap',page.locator('#chart .trend-line').get_attribute('d').count('M')==2)
    page.evaluate('data=>renderWatchTrends(data)',original)
    for i in range(4):
        panel=page.locator(f'[data-layout-id="breakdown-{i}"]')
        check(str(i)+' daily trends available',panel.locator('svg').count()==1)
        panel.locator('[data-mode="totals"]').click();check(str(i)+' totals available',panel.locator('.bar-row').first.is_visible())
        panel.locator('[data-mode="continuous"]').click();check(str(i)+' hourly timeline scrolls',panel.locator('.trend-viewport').evaluate('e=>e.scrollWidth>e.clientWidth'))
    # Delay a query to inspect centered feedback while work is actually pending.
    page.route('**/api/query',lambda route:(page.wait_for_timeout(1000),route.continue_()))
    page.evaluate('void apply()');page.locator('#activityFeedback[data-state="loading"]').wait_for(state='visible')
    box=page.locator('#activityFeedback').bounding_box()
    check('Loading feedback centered horizontally',abs(box['x']+box['width']/2-1440/2)<2)
    check('Loading feedback centered vertically',abs(box['y']+box['height']/2-1000/2)<2)
    ready();page.unroute('**/api/query')
    check('Chart mode survives data refresh',page.locator('#chart [data-mode="continuous"]').get_attribute('aria-pressed')=='true')
    page.evaluate('scrollTo(0,0)');page.screenshot(path=str(ROOT/'audit/trends_desktop.png'))
    for width in [1024,768,390,320]:
        page.set_viewport_size({'width':width,'height':900});page.wait_for_timeout(250)
        check(str(width)+' no horizontal page overflow',page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
    page.evaluate("setActivity('loading','Updating your selected audience...')")
    box=page.locator('#activityFeedback').bounding_box()
    check('Mobile loading stays centered and contained',box['x']>=0 and box['x']+box['width']<=321 and abs(box['y']+box['height']/2-450)<2)
    check('No browser errors',not errors);browser.close()
(ROOT/'audit/trends.json').write_text(json.dumps({'passed':True,'checks':checks},indent=2))
print('PASS',len(checks),'trend, snapshot and loader checks')

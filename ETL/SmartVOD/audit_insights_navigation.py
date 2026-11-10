"""Verify insight-only filter application and safe deferred dashboard refresh."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parent;checks=[]
def check(name,ok):
    assert ok,name
    checks.append(name)
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True);page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];queries=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('request',lambda r:queries.append(r.url) if r.url.endswith('/api/query') else None)
    page.goto('http://127.0.0.1:8766/');page.wait_for_function("applied!==null&&!document.getElementById('apply').disabled",timeout=120000)
    page.locator('#insightsPage').click();page.wait_for_function("!document.getElementById('insightExport').disabled",timeout=120000)
    count=len(queries);held=[];page.route('**/api/*insights',lambda r:held.append(r))
    page.evaluate('document.getElementById("start").value=meta.dates.at(-2);document.getElementById("end").value=meta.dates.at(-2);renderFilters();void apply()')
    page.wait_for_function("document.getElementById('insightContent').getAttribute('aria-busy')==='true'")
    check('Insight refresh avoids dashboard query',len(queries)==count)
    check('Stale insight content cannot be used',page.locator('#insightContent').evaluate('e=>e.inert'))
    page.locator('#dashboardPage').click()
    check('Dashboard navigation explains pending selection','Finishing' in page.locator('#insightMessage').inner_text())
    check('Dashboard remains hidden during pending analysis',page.locator('#results').is_hidden())
    held[0].continue_();page.unroute('**/api/*insights')
    page.wait_for_function("document.getElementById('dashboardPage').getAttribute('aria-pressed')==='true'&&!document.getElementById('apply').disabled",timeout=120000)
    check('Dashboard query deferred until return',len(queries)==count+1)
    check('Fresh dashboard becomes visible',page.locator('#results').is_visible())
    check('Applied day is the requested new day',page.evaluate('applied.start===meta.dates.at(-2)&&applied.end===meta.dates.at(-2)'))
    page.locator('#insightsPage').click();page.wait_for_function("!document.getElementById('insightExport').disabled",timeout=120000)
    check('Insights match applied dashboard selection',page.evaluate('document.getElementById("insightScope").textContent.includes(applied.start)'))
    page.locator('#insightQuestion').fill('trend in NeverlandXYZ');page.locator('#insightQuestionForm button').click()
    page.wait_for_function("document.getElementById('insightQuestionMessage').textContent.includes('not matched')",timeout=120000)
    check('Unmatched location is not substituted','not matched' in page.locator('#insightQuestionMessage').inner_text())
    page.locator('#insightQuestion').fill('Which ISP increased?');page.locator('#insightQuestionForm button').click()
    page.wait_for_function("!document.getElementById('insightExport').disabled",timeout=120000)
    page.wait_for_function("document.getElementById('insightTab-drivers').getAttribute('aria-selected')==='true'",timeout=120000)
    check('Question chooses matching breakdown',page.locator('#insightDimension').input_value()=='isp')
    check('Increase question activates positive movement filter',page.locator('#insightContent .trend-controls [aria-pressed=true]').inner_text()=='Increases')
    check('No JavaScript errors '+str(errors),not errors);browser.close()
(ROOT/'audit/insights_navigation.json').write_text(json.dumps({'passed':True,'checks':checks},indent=2))
print('PASS',len(checks),'insight navigation and routing checks')

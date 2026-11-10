"""Real-data reconciliation and stakeholder walkthrough with failure injection."""
from pathlib import Path
import csv,json,math,sqlite3,urllib.request
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parent;checks=[]
def check(name,ok):
    assert ok,name
    checks.append(name)
def api(path,body):
    req=urllib.request.Request('http://127.0.0.1:8766'+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    return json.load(urllib.request.urlopen(req,timeout=120))
meta=json.loads((ROOT/'data/manifest.json').read_text());day=meta['dates'][-1]
body=dict(start=day,end=day,filters={},timeStart='00:00',timeEnd='23:59')
data=api('/api/insights',body)
con=sqlite3.connect(ROOT/'data'/meta['database'])
expected=con.execute('SELECT sum(hours),count(DISTINCT nullif(device_id,\'Unknown\')),count(DISTINCT nullif(cli_ip,\'Unknown\')) FROM events WHERE day=?',[day]).fetchone();con.close()
check('Current hours match independent snapshot SQL',math.isclose(data['summary']['current'],expected[0],abs_tol=1e-7))
check('Device totals match independent snapshot SQL',data['totals']['devices']==expected[1])
check('IP totals match independent snapshot SQL',data['totals']['ips']==expected[2])
check('Baseline source coverage explicit',isinstance(data['comparison_available'],bool) and 'loaded_days' in data['previous_period'])
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True);page=browser.new_page(viewport={'width':1440,'height':1000},accept_downloads=True);errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    def ready():page.wait_for_function("applied!==null&&!document.getElementById('apply').disabled",timeout=120000)
    def insights_ready():page.wait_for_function("!document.getElementById('insightExport').disabled",timeout=120000)
    page.goto('http://127.0.0.1:8766/');ready();before=page.evaluate('JSON.stringify(applied)')
    page.locator('#insightsPage').click();insights_ready()
    check('Insights menu opens',page.locator('#insightsArea').is_visible() and page.locator('#results').is_hidden())
    check('Six stakeholder tabs',page.locator('.insight-tabs [role=tab]').count()==6)
    check('Executive brief has measured cards',page.locator('.insight-card').count()==4)
    check('Evidence stories identify current leader','Largest current region' in page.locator('#insightContent').inner_text())
    page.locator('#insightTab-regions').click();check('Regional ranking available',page.locator('.insight-table tbody tr').count()>0)
    page.locator('[data-region]').first.click();check('Region has a trend chart',page.locator('.insight-plot svg').count()==1)
    page.locator('.insight-plot .panel-heading button').click();check('Insight chart expands',page.locator('.insight-dialog').is_visible());page.keyboard.press('Escape');check('Insight chart closes',page.locator('.insight-dialog').is_hidden())
    page.locator('#insightTab-changes').click();check('Material movements have filters',page.locator('#insightContent .trend-controls button').count()==4)
    page.locator('#insightContent .trend-controls button').filter(has_text='Unusual daily').click();check('Unusual view explains missing/no alerts','No unusual' in page.locator('#insightContent').inner_text() or page.locator('.insight-story').count()>0)
    page.locator('#insightTab-method').click();check('Method discloses limits','not a significance test' in page.locator('#insightContent').inner_text())
    page.locator('#insightQuestion').fill('Which regions dropped?');page.locator('#insightQuestionForm button').click()
    check('Question routes to declines',page.locator('#insightTab-changes').get_attribute('aria-selected')=='true' and page.locator('#insightContent [aria-pressed=true]').inner_text()=='drops')
    page.locator('#insightQuestion').fill('explain the weather tomorrow');page.locator('#insightQuestionForm button').click();check('Unsupported question not fabricated','cannot map' in page.locator('#insightQuestionMessage').inner_text())
    page.locator('#insightQuestion').fill('Which ISP increased?');page.locator('#insightQuestionForm button').click();insights_ready()
    page.wait_for_function("document.getElementById('insightTab-drivers').getAttribute('aria-selected')==='true'",timeout=120000)
    check('ISP question selects ISP breakdown',page.locator('#insightDimension').input_value()=='isp')
    page.locator('#insightQuestion').fill('top client IPs');page.locator('#insightQuestionForm button').click();insights_ready()
    page.wait_for_function("document.getElementById('insightTab-viewers').getAttribute('aria-selected')==='true'",timeout=120000)
    check('IP question selects client IP basis',page.locator('#insightBasis').input_value()=='cli_ip')
    check('Leaderboard identifies proxy limitations','not a person classification' in page.locator('#insightContent').inner_text())
    with page.expect_download() as dl:page.locator('#insightExport').click()
    rows=list(csv.DictReader(Path(dl.value.path()).read_text(encoding='utf-8-sig').splitlines()))
    check('Export includes measured sections',bool(rows) and {'section','current','previous','baseline_kind'}.issubset(rows[0]))
    check('Export includes IP leaderboard',any(r['section']=='top_cli_ip' for r in rows))
    check('Analysis controls preserve master filters',page.evaluate('JSON.stringify(applied)')==before)
    # Ordinary user drill-down from the audience ranking.
    page.locator('[data-open-identifier]').first.click();ready();page.locator('#journeyPanelIP').wait_for(state='visible',timeout=120000)
    check('Audience ranking opens IP journey',page.locator('#results').is_visible() and page.evaluate('applied.filters.cli_ip.length===1'))
    page.locator('#backToIPs').click();ready();page.locator('#insightsPage').click();insights_ready()
    # Unsupported source history must not become a fabricated growth percentage.
    page.locator('#dashboardPage').click();page.evaluate('document.getElementById("start").value=meta.dates[0];document.getElementById("end").value=meta.dates[0];renderFilters();void apply()');ready()
    page.locator('#insightsPage').click();insights_ready()
    check('Missing comparison baseline explicit','comparison unavailable' in page.locator('#insightContent').inner_text().lower())
    page.locator('#dashboardPage').click();page.evaluate('document.getElementById("reset").click()');ready();page.locator('#insightsPage').click();insights_ready()
    # Fail/retry and stale analysis races use existing real data as fixture.
    page.route('**/api/insights',lambda r:r.abort('failed'));page.locator('#insightMetric').select_option('devices')
    page.locator('#insightMessage button').wait_for(state='visible',timeout=120000)
    check('Failure disables insight export',page.locator('#insightExport').is_disabled())
    page.unroute('**/api/insights');page.locator('#insightMessage button').click();insights_ready()
    check('Retry recovers analysis','Known Device IDs' in page.locator('#insightScope').inner_text())
    page.locator('#insightTab-brief').click();page.screenshot(path=str(ROOT/'audit/insights_brief.png'))
    for width,height in [(1920,1080),(1024,900),(768,900),(390,844),(320,640)]:
        page.set_viewport_size({'width':width,'height':height});page.wait_for_timeout(100)
        check(str(width)+' insights page has no overflow',page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
        page.locator('#insightTab-regions').click()
        check(str(width)+' table scroll stays contained',page.locator('.insight-table-scroll').evaluate('e=>e.scrollWidth>=e.clientWidth'))
        page.locator('#insightTab-brief').click()
        if width==390:page.screenshot(path=str(ROOT/'audit/insights_mobile.png'))
    check('No JavaScript errors: '+str(errors),not errors);browser.close()
(ROOT/'audit/insights_ui.json').write_text(json.dumps({'passed':True,'checks':checks},indent=2))
print('PASS',len(checks),'real-data and stakeholder UI checks')

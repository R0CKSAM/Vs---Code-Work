import csv,json
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path('ETL/SmartVOD');checks=[];errors=[]
def check(n,ok):
 assert ok,n
 checks.append(n)
with sync_playwright() as p:
 b=p.chromium.launch(channel='msedge',headless=True);page=b.new_page(viewport={'width':1440,'height':1000},accept_downloads=True);page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto('http://127.0.0.1:8766');page.wait_for_function("document.getElementById('status').textContent.includes('matched records')",timeout=60000)
 check('Record note separators readable','?' not in page.locator('#status').text_content())
 page.locator('#deviceExplorer .device-card').first.click();page.locator('#journeyContent').wait_for(state='visible',timeout=60000)
 check('Device drill-down succeeds with guarded apply',page.evaluate('applied.filters.device_id.length===1'))
 page.locator('#ipExplorer .device-card').first.click();page.locator('#journeyContentIP').wait_for(state='visible',timeout=60000);page.locator('#journeyContent').wait_for(state='visible',timeout=60000)
 check('Both journeys visible',page.locator('#journeyContent').is_visible() and page.locator('#journeyContentIP').is_visible())
 check('Both ID filters stay active',page.evaluate('applied.filters.device_id.length===1&&applied.filters.cli_ip.length===1'))
 old_ip=page.locator('#journeyPositionIP').text_content();old_device=page.locator('#journeyPosition').text_content()
 if not page.locator('#journeyNextMatch').is_disabled():
  page.locator('#journeyNextMatch').click()
  check('Device navigation changes selected session',page.locator('#journeyPosition').text_content()!=old_device)
  check('Device navigation does not alter IP journey',page.locator('#journeyPositionIP').text_content()==old_ip)
 for suffix,basis in [('', 'device_id'),('IP','cli_ip')]:
  with page.expect_download() as dl:page.locator('#journeyExport'+suffix).click()
  rows=list(csv.DictReader(Path(dl.value.path()).read_text(encoding='utf-8-sig').splitlines()))
  value=page.evaluate('applied.filters.'+basis+'[0]')
  check(basis+' export correct basis and identifier',bool(rows) and all(r['identity_basis']==basis and r['identity_value']==value for r in rows))
 page.screenshot(path=str(ROOT/'audit/final_journeys.png'))
 check('No journey browser errors',not errors);b.close()
(ROOT/'audit/final_journeys.json').write_text(json.dumps({'passed':True,'checks':checks,'errors':errors},indent=2));print('PASS',len(checks),'final journey checks')

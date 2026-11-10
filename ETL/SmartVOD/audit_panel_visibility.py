"""Verify conditional journey panels, simplified menu, responsive chart widths."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parent;checks=[]
def check(name,ok):
    assert ok,name
    checks.append(name)
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8766/')
    page.wait_for_function("applied!==null&&!document.getElementById('apply').disabled",timeout=120000)
    for panel in ['journeyPanel','journeyPanelIP']:
        check(panel+' hidden by default',page.locator('#'+panel).is_hidden())
        check(panel+' has no empty wrapper',page.locator('#'+panel).evaluate("e=>e.closest('.layout-tile').hidden"))
    check('Spacing control removed',page.locator('#density').count()==0)
    page.locator('#advancedToggle').click();page.locator('#closeAdvanced').wait_for(state='visible')
    check('Workspace heading removed','Workspace' not in page.locator('.drawer-tools').inner_text())
    check('Layout editor retained',page.locator('#layoutToggle').is_visible())
    page.locator('#closeAdvanced').click()
    device=page.locator('#deviceExplorer .device-card').first.get_attribute('data-identity-value')
    ips=page.locator('#ipExplorer .device-card').evaluate_all('(es)=>es.slice(0,2).map(e=>e.dataset.identityValue)')
    page.evaluate("id=>{draft.device_id=new Set([id]);renderFilters()}",device)
    check('Draft selection does not show a journey',page.locator('#journeyPanel').is_hidden())
    page.evaluate('apply()');page.wait_for_function("!document.getElementById('apply').disabled",timeout=120000)
    check('One device shows device journey',page.locator('#journeyPanel').is_visible())
    check('IP journey stays hidden',page.locator('#journeyPanelIP').is_hidden())
    page.evaluate("ips=>{draft.device_id.clear();draft.cli_ip=new Set([ips[0]]);renderFilters();apply()}",ips)
    page.wait_for_function("!document.getElementById('apply').disabled",timeout=120000)
    check('One IP shows IP journey',page.locator('#journeyPanelIP').is_visible())
    check('Cleared device hides device journey',page.locator('#journeyPanel').is_hidden())
    page.evaluate("ips=>{draft.cli_ip=new Set(ips);renderFilters();apply()}",ips)
    page.wait_for_function("!document.getElementById('apply').disabled",timeout=120000)
    check('Multiple identifiers hide journey',page.locator('#journeyPanelIP').is_hidden())
    page.evaluate("draft.cli_ip=new Set(['Unknown']);renderFilters();apply()")
    page.wait_for_function("!document.getElementById('apply').disabled",timeout=120000)
    check('Unknown identifier hides journey',page.locator('#journeyPanelIP').is_hidden())
    page.evaluate("document.getElementById('reset').click()")
    page.wait_for_function("!document.getElementById('apply').disabled",timeout=120000)
    for width in [1920,1440,1199,1024,768,390,320]:
        page.set_viewport_size({'width':width,'height':1000});page.wait_for_timeout(100)
        chart=page.locator('[data-layout-id="chart-0"]').bounding_box()
        delivery=page.locator('[data-layout-id="chart-1"]').bounding_box()
        available=page.locator('#results').bounding_box()['width']
        if width>=1200:
            check(str(width)+' chart gets at least 60 percent',chart['width']/available>=.6)
        else:
            check(str(width)+' chart spans full row',abs(chart['width']-available)<=1)
            check(str(width)+' delivery below chart',delivery['y']>=chart['y']+chart['height'])
        check(str(width)+' no page overflow',page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
    check('No browser errors',not errors);browser.close()
(ROOT/'audit/panel_visibility.json').write_text(json.dumps({'passed':True,'checks':checks},indent=2))
print('PASS',len(checks),'visibility and responsive panel checks')

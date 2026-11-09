from pathlib import Path
import json
from playwright.sync_api import sync_playwright
ROOT=Path('ETL/SmartVOD');checks=[];errors=[]
def check(n,ok):
 assert ok,n
 checks.append(n)
with sync_playwright() as p:
 b=p.chromium.launch(channel='msedge',headless=True);page=b.new_page(viewport={'width':1440,'height':1000});page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto('http://127.0.0.1:8766')
 def ready():page.wait_for_function("applied!==null&&!document.getElementById('apply').disabled",timeout=90000)
 ready()
 region=page.evaluate("async()=>{const id=document.querySelector('#deviceExplorer .device-card').dataset.identityValue;return(await(await request('/api/facet',{...applied,field:'region',filters:{device_id:[id]}})).json()).options[0].value}")
 page.evaluate('(region)=>{draft.region=new Set([region]);renderFilters();return apply()}',region);ready()
 baseline=page.evaluate('JSON.stringify(applied)');count=page.locator('#deviceExplorer .device-card').count()
 page.locator('#deviceExplorer').evaluate('(e)=>e.scrollTop=160')
 index=min(6,count-1);chosen=page.locator('#deviceExplorer .device-card').nth(index)
 chosen.scroll_into_view_if_needed();position=page.locator('#deviceExplorer').evaluate('(e)=>e.scrollTop');identifier=chosen.get_attribute('data-identity-value')
 chosen.click();ready();page.locator('#journeyContent').wait_for(state='visible',timeout=60000)
 check('Journey offers Back to device list',page.locator('#backToDevices').is_visible())
 check('Drill-down narrows device list',page.locator('#deviceExplorer .device-card').count()==1)
 page.locator('#backToDevices').click();ready();page.wait_for_timeout(650)
 check('Back restores original filters',page.evaluate('JSON.stringify(applied)')==baseline)
 check('Back restores full previous device list',page.locator('#deviceExplorer .device-card').count()==count)
 check('Back restores list scroll position',abs(page.locator('#deviceExplorer').evaluate('(e)=>e.scrollTop')-position)<=2)
 check('Back restores focus to selected card',page.evaluate('document.activeElement.dataset.identityValue')==identifier)
 bar=page.locator('.master-filters').bounding_box();panel=page.locator('#devicePanel').bounding_box()
 check('Explorer heading remains below toolbar',panel['y']>=bar['y']+bar['height']-2)
 # Device -> IP journey -> IP list -> original device list.
 page.locator('#deviceExplorer .device-card').nth(index).click();ready();page.locator('#ipExplorer .device-card').first.click();ready()
 page.locator('#journeyContentIP').wait_for(state='visible',timeout=60000)
 check('Nested journey has both selected IDs',page.evaluate('applied.filters.device_id.length===1&&applied.filters.cli_ip.length===1'))
 page.locator('#backToIPs').click();ready()
 check('IP Back restores device-scoped explorer',page.evaluate('applied.filters.device_id.length===1&&applied.filters.cli_ip.length===0'))
 page.locator('#backToDevices').click();ready()
 check('Device Back completes nested return',page.evaluate('JSON.stringify(applied)')==baseline)
 # A failed return keeps its history so retrying the same Back button works.
 page.locator('#deviceExplorer .device-card').nth(index).click();ready()
 narrowed=page.evaluate('JSON.stringify(applied)')
 page.route('**/api/query',lambda r:r.abort('failed'));page.locator('#backToDevices').click();ready()
 check('Failed Back keeps current applied view',page.evaluate('JSON.stringify(applied)')==narrowed)
 page.unroute('**/api/query');page.locator('#backToDevices').click();ready()
 check('Failed Back can be retried without losing history',page.evaluate('JSON.stringify(applied)')==baseline)
 # Direct identifier filters have a sensible return even without a click history.
 page.evaluate('(id)=>{clearExplorerHistory();draft.device_id=new Set([id]);renderFilters();return apply()}',identifier);ready()
 page.locator('#backToDevices').click();ready()
 check('Direct-filter Back clears only the identifier',page.evaluate('JSON.stringify(applied)')==baseline)
 page.set_viewport_size({'width':390,'height':844})
 check('Mobile return controls fit',page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
 check('Mobile Back is a usable touch target',page.locator('#backToDevices').bounding_box()['height']>=40)
 page.screenshot(path=str(ROOT/'audit/explorer_return_mobile.png'))
 check('No browser errors',not errors);b.close()
(ROOT/'audit/explorer_return.json').write_text(json.dumps({'passed':True,'checks':checks,'errors':errors},indent=2));print('PASS',len(checks),'explorer return checks')

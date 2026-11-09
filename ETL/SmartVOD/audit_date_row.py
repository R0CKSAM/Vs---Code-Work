from pathlib import Path
import json,datetime
from playwright.sync_api import sync_playwright
ROOT=Path('ETL/SmartVOD');checks=[];errors=[]
def check(name,ok):
 assert ok,name
 checks.append(name)
with sync_playwright() as p:
 b=p.chromium.launch(channel='msedge',headless=True);page=b.new_page(viewport={'width':1440,'height':1000})
 page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto('http://127.0.0.1:8766');page.wait_for_function("document.getElementById('status').textContent.includes('matched records')",timeout=60000)
 check('Quick filters heading removed',page.locator('.quick-label').count()==0)
 check('One visible date selector',page.locator('#rangePicker').count()==1 and page.locator('#start').is_hidden() and page.locator('#end').is_hidden())
 check('Revenue calendar library loaded',page.evaluate("typeof flatpickr==='function'"))
 dates=page.evaluate('meta.dates');start,end=dates[-2],dates[-1]
 def aria(day):
  dt=datetime.date.fromisoformat(day);return dt.strftime('%B')+' '+str(dt.day)+', '+str(dt.year)
 page.locator('#rangeTitle').click();page.locator('#rangePanel').wait_for(state='visible')
 page.locator('.flatpickr-day[aria-label="'+aria(start)+'"]').click()
 page.locator('.flatpickr-day[aria-label="'+aria(end)+'"]').click()
 page.locator('#applyDateRange').click()
 check('Two calendar clicks set from/to',page.locator('#start').input_value()==start and page.locator('#end').input_value()==end)
 check('Date change remains pending','Pending changes' in page.locator('#status').inner_text())
 page.locator('#apply').click();page.wait_for_function("!document.getElementById('apply').disabled",timeout=60000)
 check('Date range applied to query',page.evaluate(f"applied.start==='{start}' && applied.end==='{end}'"))
 page.locator('#rangeTitle').click();page.locator('#allDateRange').click();page.locator('#cancelDateRange').click()
 check('Cancel preserves date range',page.locator('#start').input_value()==start)
 page.locator('#rangeTitle').click();page.locator('#latestDateRange').click();page.locator('#applyDateRange').click()
 check('Latest-day preset',page.locator('#start').input_value()==end and page.locator('#end').input_value()==end)
 page.locator('#rangeTitle').click();page.locator('#weekDateRange').click();page.locator('#applyDateRange').click()
 check('Week preset inclusive seven days',(datetime.date.fromisoformat(page.locator('#end').input_value())-datetime.date.fromisoformat(page.locator('#start').input_value())).days==6)
 page.locator('#rangeTitle').click();page.locator('#allDateRange').click();page.locator('#applyDateRange').click()
 check('All-range preset',page.locator('#start').input_value()==dates[0] and page.locator('#end').input_value()==dates[-1])
 page.locator('#reset').click();page.wait_for_function("!document.getElementById('apply').disabled",timeout=60000)
 check('Reset refreshes range label',page.locator('#rangeText').inner_text().count('04 Nov 2026')==2)
 page.locator('#rangeTitle').click();page.keyboard.press('Escape')
 check('Escape closes dates and restores focus',not page.locator('#rangePicker').evaluate('(e)=>e.open') and page.locator('#rangeTitle').evaluate('(e)=>document.activeElement===e'))
 page.evaluate("draft.title=new Set(['An exceptionally long programme title with episode information and a long identifier abcdefghijklmnopqrstuvwxyz012345678901234567890123456789']);renderFilters()")
 for width in [1920,1440,1280,1024,768,600,390,320]:
  page.set_viewport_size({'width':width,'height':900});page.wait_for_timeout(100)
  check(f'{width} no page overflow',page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
  check(f'{width} text fits every filter',page.evaluate("[...document.querySelectorAll('.basic-filter-grid .filter-trigger,.basic-filter-grid summary')].every(e=>e.scrollWidth<=e.clientWidth+1&&e.scrollHeight<=e.clientHeight+1)"))
  box=page.locator('.basic-filter-grid').bounding_box();actions=page.locator('.quick-toolbar').bounding_box()
  check(f'{width} actions below filters',actions['y']>=box['y']+box['height']-1)
  if width>=1280:
   positions=page.locator('.basic-filter-grid .field, .range-field').evaluate_all('(nodes)=>nodes.map(e=>Math.round(e.getBoundingClientRect().top))')
   check(f'{width} five filters in one row',len(set(positions))==1)
  page.locator('#rangeTitle').click();page.wait_for_timeout(100)
  panel=page.locator('#rangePanel').bounding_box()
  check(f'{width} date popup fits',panel['x']>=0 and panel['x']+panel['width']<=width+1 and panel['y']>=0 and panel['y']+panel['height']<=901)
  page.keyboard.press('Escape')
  if width in [1440,390]:page.screenshot(path=str(ROOT/f'audit/date_row_{width}.png'))
 page.evaluate('draft.title.clear();renderFilters()')
 check('No JS errors',not errors);b.close()
(ROOT/'audit/date_row.json').write_text(json.dumps({'passed':True,'checks':checks,'errors':errors},indent=2))
print('PASS',len(checks),'checks')

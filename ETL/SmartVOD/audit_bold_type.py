from pathlib import Path
import json
from playwright.sync_api import sync_playwright
ROOT=Path('ETL/SmartVOD');checks=[];errors=[]
def check(n,ok):
 assert ok,n
 checks.append(n)
with sync_playwright() as p:
 b=p.chromium.launch(channel='msedge',headless=True);page=b.new_page(viewport={'width':1440,'height':1000});page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto('http://127.0.0.1:8766');page.wait_for_function("applied!==null&&!document.getElementById('apply').disabled",timeout=90000)
 check('KPI numbers large and bold',page.locator('#hours').evaluate('(e)=>parseFloat(getComputedStyle(e).fontSize)>=32&&Number(getComputedStyle(e).fontWeight)>=700'))
 check('Average figures bold',page.locator('#averageMinutes').evaluate('(e)=>Number(getComputedStyle(e).fontWeight)>=700'))
 for width,height in [(1920,1000),(1440,1000),(768,900),(390,844),(320,640),(844,390)]:
  page.set_viewport_size({'width':width,'height':height});page.wait_for_timeout(200)
  check(f'{width} no horizontal overflow',page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
  check(f'{width} KPI text contained',page.locator('.kpis article').evaluate_all('(es)=>es.every(e=>e.scrollWidth<=e.clientWidth+1)'))
  check(f'{width} header text contained',page.locator('#rangeTitle,#filter-title,#advancedToggle').evaluate_all('(es)=>es.every(e=>e.scrollWidth<=e.clientWidth+1)'))
  page.locator('#filter-title').click();page.locator('#options input').first.wait_for();rect=page.locator('#done').bounding_box()
  check(f'{width} picker action reachable',rect['y']>=0 and rect['y']+rect['height']<=height+1)
  page.locator('#cancelPicker').click();page.wait_for_timeout(200)
  if width in [1440,390]:page.screenshot(path=str(ROOT/f'audit/bold_type_{width}.png'))
 check('No browser errors',not errors);b.close()
(ROOT/'audit/bold_type.json').write_text(json.dumps({'passed':True,'checks':checks,'errors':errors},indent=2));print('PASS',len(checks),'typography checks')

"""Exercise independent resize axes, cancellation, typography and overflow."""
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
    check('No standalone Layout control',not page.locator('#layoutToggle').is_visible())
    check('Layout is inside More filters',page.locator('#advancedDrawer #layoutToggle').count()==1)
    page.locator('#advancedToggle').click();page.locator('#layoutToggle').click()
    check('Editing closes drawer',page.locator('#advancedToggle').get_attribute('aria-expanded')=='false')
    check('Editing has Done action',page.locator('#layoutDone').is_visible())
    tile=page.locator('[data-layout-id="kpi-0"]')
    def state():
        return tile.evaluate("e=>({width:e.style.getPropertyValue('--tile-span'),height:e.style.getPropertyValue('--tile-height')})")
    def drag(selector,dx,dy,cancel=False):
        grip=tile.locator(selector);grip.scroll_into_view_if_needed();box=grip.bounding_box()
        x=box['x']+box['width']/2;y=box['y']+box['height']/2
        page.mouse.move(x,y);page.mouse.down();page.mouse.move(x+dx,y+dy,steps=12)
        if cancel:page.keyboard.press('Escape')
        page.mouse.up();page.wait_for_timeout(250)
    original=state();drag('.layout-resize-x',115,35);horizontal=state()
    check('Horizontal handle changes width',horizontal['width']!=original['width'])
    check('Horizontal handle preserves height',horizontal['height']==original['height'])
    drag('.layout-resize-y',60,70);vertical=state()
    check('Vertical handle changes height',vertical['height']!=horizontal['height'])
    check('Vertical handle preserves width',vertical['width']==horizontal['width'])
    drag('.layout-resize-both',100,60);both=state()
    check('Corner changes both dimensions',both['width']!=vertical['width'] and both['height']!=vertical['height'])
    drag('.layout-resize-both',100,30,cancel=True)
    check('Escape rolls back resize',state()==both)
    check('Resize controls have no emoji or text',tile.locator('.layout-resize').evaluate_all('(es)=>es.every(e=>e.textContent==="")'))
    check('Glass backdrop enabled',tile.locator('article').evaluate('(e)=>getComputedStyle(e).backdropFilter.includes("blur")'))
    page.locator('#advancedToggle').click();page.locator('#layoutReset').click();page.locator('#closeAdvanced').click()
    page.locator('#layoutDone').click()
    for width,height in [(1920,1080),(1024,900),(768,900),(390,844),(320,640)]:
        page.set_viewport_size({'width':width,'height':height});page.wait_for_timeout(200)
        check(str(width)+' KPI numbers fit',page.locator('.kpis strong').evaluate_all('(es)=>es.every(e=>e.scrollWidth<=e.clientWidth+1)'))
        check(str(width)+' KPI labels fit',page.locator('.kpis label,.kpis small').evaluate_all('(es)=>es.every(e=>e.scrollWidth<=e.clientWidth+1)'))
        check(str(width)+' page fits',page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
    page.set_viewport_size({'width':1440,'height':1000})
    page.locator('#hours').evaluate('(e)=>e.textContent="12,34,56,789.99"');page.wait_for_timeout(200)
    check('Large KPI automatically fits',page.locator('#hours').evaluate('e=>e.scrollWidth<=e.clientWidth+1&&parseFloat(getComputedStyle(e).fontSize)<42'))
    page.locator('#advancedToggle').click();page.locator('#layoutToggle').click()
    content=page.locator('[data-layout-id="content"]');content.locator('.layout-resize-y').focus();page.keyboard.press('ArrowUp');page.wait_for_timeout(200)
    check('Overflow content has scrollbars',content.locator('.layout-content').evaluate('e=>getComputedStyle(e).overflowY==="auto"&&e.scrollHeight>e.clientHeight'))
    page.locator('#layoutDone').click()
    page.evaluate('apply()');page.wait_for_function("!document.getElementById('apply').disabled",timeout=120000)
    page.screenshot(path=str(ROOT/'audit/layout_glass_desktop.png'))
    page.set_viewport_size({'width':390,'height':844});page.evaluate('scrollTo(0,0)');page.wait_for_timeout(200);page.screenshot(path=str(ROOT/'audit/layout_glass_mobile.png'))
    page.evaluate("()=>{Storage.prototype.setItem=function(){throw new Error('Browser storage blocked')}}")
    page.locator('#advancedToggle').click();page.locator('#layoutToggle').click()
    page.locator('[data-layout-id="kpi-0"] .layout-handle').focus();page.keyboard.press('Shift+ArrowRight');page.wait_for_timeout(300)
    check('Blocked storage warning visible while editing',page.locator('.layout-edit-status').is_visible() and 'Cannot save' in page.locator('.layout-edit-status').inner_text())
    check('Blocked storage keeps editing usable',page.locator('[data-layout-id="kpi-0"]').evaluate("e=>e.style.getPropertyValue('--tile-span')==='4'"))
    check('No browser errors',not errors);browser.close()
(ROOT/'audit/layout_axes.json').write_text(json.dumps({'passed':True,'checks':checks},indent=2))
print('PASS',len(checks),'axis, typography and glass checks')

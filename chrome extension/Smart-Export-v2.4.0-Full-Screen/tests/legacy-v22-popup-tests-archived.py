"""Smart Export 2.2: production-style interaction and layout regression suite.
No live Grafana connection: browser mocks content and Chrome APIs.
"""
import asyncio,base64,pathlib,importlib.util,re,json
from playwright.async_api import async_playwright
ROOT=pathlib.Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('mock_suite',ROOT/'tests/fixture-v22.py')
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
MOCK=fixture.MOCK
bundle=fixture.bundle

def passed(check,label):
    if not check:raise AssertionError(label)
    print('PASS',label)

def check_layout_script():
    return '''() => {
      let visible = [...document.querySelectorAll('button,input,select,[role=tab]')].filter(x=>x.getClientRects().length && getComputedStyle(x).visibility!=='hidden');
      let collisions=visible.filter(x=>{let r=x.getBoundingClientRect(); return r.right > 520.5 || r.left < -.5;});
      const areas=['.shell','.topbar','.page-tabs','.workbench','.feedback-wrap','.dock'].map(s=>document.querySelector(s).getBoundingClientRect());
      return {rootWidth:document.documentElement.scrollWidth,clientWidth:document.documentElement.clientWidth,
          appWidth:areas[0].width,appHeight:areas[0].height,
          scrollWidth:document.querySelector('.workbench').scrollWidth,
          scrollClient:document.querySelector('.workbench').clientWidth,
          controlsOut:collisions.map(x=>x.id||x.textContent.trim().slice(0,35)),
          end:areas[5].bottom,start:areas[0].top,
          navH:areas[2].height,dockTop:areas[5].top,feedbackTop:areas[4].top,
          duplicateIds: [...document.querySelectorAll('[id]')].map(x=>x.id).filter((id,i,a)=>a.indexOf(id)<i)};
    }'''

async def run():
  html=(ROOT/'popup.html').read_text();css=(ROOT/'popup.css').read_text()
  img='data:image/png;base64,'+base64.b64encode((ROOT/'icons/icon48.png').read_bytes()).decode()
  html=html.replace('<link rel="stylesheet" href="popup.css">','<style>'+css+'</style>')
  html=html.replace('<script type="module" src="popup.mjs"></script>','').replace('src="icons/icon48.png"',f'src="{img}"')
  async with async_playwright() as p:
    browser=await p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--disable-gpu'])
    context=await browser.new_context(viewport={'width':520,'height':600},device_scale_factor=1,accept_downloads=True)
    page=await context.new_page();errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('dialog',lambda d:asyncio.create_task(d.accept()))
    await page.set_content(html,wait_until='domcontentloaded');await page.add_script_tag(content=bundle())
    await page.locator('.category-btn').first.wait_for()
    await page.screenshot(path='/mnt/data/Smart-Export-v2.2.0-Choose-Data.png')
    geo=await page.evaluate(check_layout_script())
    passed(geo['appWidth']==520 and geo['appHeight']==600 and geo['rootWidth']==520,'Stable 520 × 600 extension root')
    passed(not geo['duplicateIds'],'No duplicate IDs')
    passed(not geo['controlsOut'] and geo['scrollWidth']==geo['scrollClient'],'No horizontally overflowing visible controls')
    passed(await page.locator('.page-tab.active').count()==1,'Exactly one active navigation tab')
    passed(await page.locator('.category-btn').count()==6,'Six stable metric categories visible')
    passed(await page.locator('.quick-btn').count()==6,'Six quick presets visible')
    passed(await page.locator('#selectedCount').inner_text()=='5 metrics','Default selection is clearly labelled')
    passed(not await page.locator('#view-results').is_visible(),'Results view hidden until selected')
    passed(await page.locator('#dockFetch').is_visible(),'Fetch button stays visible without scrolling')
    
    # Picker interactions with no accordion collapse, scroll and focus safe.
    await page.locator('.category-btn[data-category="channel"]').click()
    passed('Channels' in await page.locator('#catalogTitle').inner_text(),'Category switching works')
    input=page.locator('#metricCatalog input[data-report="channel"]').first
    await input.scroll_into_view_if_needed()
    scroll_before=await page.locator('#metricCatalog').evaluate('(e)=>e.scrollTop')
    await input.click()
    await page.wait_for_timeout(70)
    passed(await input.evaluate('(x)=>x===document.activeElement'),'Checking a metric keeps keyboard focus')
    passed(abs((await page.locator('#metricCatalog').evaluate('(e)=>e.scrollTop'))-scroll_before)<8,'Selecting a metric does not jump the list')
    passed(await page.locator('.category-btn.active').get_attribute('data-category')=='channel','Selected category remains active')
    await page.locator('#metricSearch').fill('playtime')
    passed(await page.locator('.metric-group-heading').count()>=2,'Search finds metrics across groups')
    await page.locator('#clearSearch').click()
    passed('Channels' in await page.locator('#catalogTitle').inner_text(),'Clear search restores chosen category')
    await page.locator('#moreTemplates').click()
    await page.locator('button[data-preset="all"]').click()
    passed(await page.locator('#selectedCount').inner_text()=='21 metrics','All supported metrics can be selected')
    g=await page.evaluate(check_layout_script());passed(not g['controlsOut'],'21 selected metrics cannot bleed outside popup')
    await page.locator('button[data-preset="geo"]').click()
    passed(await page.locator('#selectedCount').inner_text()=='1 metric','Quick preset changes selection')
    
    # Page navigation + results filter + date + source.
    await page.locator('#tabResults').click()
    passed(await page.locator('#view-results').is_visible(),'Preview & Export navigation works')
    passed(not await page.locator('#view-build').is_visible(),'Inactive Build content hidden')
    passed(await page.locator('#exportFilterBox').is_visible(),'Dimension filter shown for compatible selection')
    a=await page.evaluate('''() => {let a=document.querySelector('#filterField').getBoundingClientRect(),b=document.querySelector('#exportFilterBox .chevron').getBoundingClientRect();return {dy:Math.abs((a.top+a.bottom)/2-(b.top+b.bottom)/2),right:a.right-b.right}}''')
    passed(a['dy']<6 and 8<a['right']<26,'Native filter dropdown caret centered and aligned')
    await page.screenshot(path='/mnt/data/Smart-Export-v2.2.0-Preview.png')
    await page.locator('#tabBuild').click()
    await page.locator('#dashboardUrl').fill(fixture.URL)
    await page.locator('#tabResults').click()
    await page.locator('#syncNow').click()
    await page.wait_for_timeout(60)
    passed(await page.locator('#syncNow').is_disabled(),'In-flight Fetch disables duplicate submission')
    passed(await page.locator('#dockFetch').is_disabled(),'Sticky Fetch also disabled during query')
    await page.wait_for_timeout(950)
    passed(await page.locator('#syncNow').is_enabled(),'Fetch recovers afterward')
    passed(await page.locator('#downloadXlsx').is_enabled(),'Excel enabled when data is ready')
    passed(await page.locator('#rowCount').inner_text()=='1','Fetched records appear in preview')
    async with page.expect_download() as received:await page.locator('#downloadXlsx').click()
    f=await received.value;dest='/mnt/data/Smart-Export-v2.2.0-Functional-Test.xlsx';await f.save_as(dest)
    passed(pathlib.Path(dest).stat().st_size>2000,'Generated Excel is nonempty')
    await page.screenshot(path='/mnt/data/Smart-Export-v2.2.0-Data-Fetched.png')
    
    # Saved views, auto schedule, logs, edge case text, panel explorer.
    await page.locator('#tabAutomation').click()
    passed(await page.locator('#view-automation').is_visible(),'Settings navigation works')
    view='My Weekly Channel and Audience Data'
    await page.locator('#presetName').fill(view)
    await page.locator('#savePreset').click()
    passed(await page.locator('#savedPresets').input_value()==view,'Saved view persists and is selected')
    rect=await page.evaluate('''() => {let s=document.querySelector('#savedPresets').getBoundingClientRect();let a=document.querySelector('#loadPreset').getBoundingClientRect();return {selectWidth:s.width,actionsBelow:a.top-s.bottom}}''')
    passed(rect['selectWidth']>300 and rect['actionsBelow']>=5,'Saved view dropdown full width, actions below')
    await page.locator('button[data-preset="channel"]').evaluate('(e)=>e.click()')
    await page.locator('#loadPreset').click()
    passed(await page.locator('#view-build').is_visible(),'Load selection returns user to report builder')
    await page.locator('#tabAutomation').click()
    await page.locator('#advancedSettings > summary').click()
    await page.locator('#scanPanels').click()
    passed(await page.locator('.panel-item').count()==2,'Panel explorer renders mapped/unmapped panels')
    async with page.expect_download() as logs:await page.locator('#logs').click()
    log=await logs.value;passed(log.suggested_filename.endswith('.json'),'Error-log export works')
    await page.screenshot(path='/mnt/data/Smart-Export-v2.2.0-Settings.png')
    
    # Stress: extremely long URLs, errors, preset labels, and filter strings.
    await page.locator('#tabBuild').click()
    await page.locator('#dashboardUrl').fill(fixture.URL+'a'*1000)
    await page.locator('#tabAutomation').click()
    await page.locator('#feedback').evaluate('(x)=>{x.textContent="A_VERY_LONG_ERROR_"+"X".repeat(1800); x.className="feedback error";}')
    await page.locator('#savedPresets').evaluate('(x)=>{let e=document.createElement("option");e.textContent="VeryVeryVeryLongNameWithoutSpaces".repeat(8);e.value="testlong";x.append(e);x.value="testlong"}')
    g=await page.evaluate(check_layout_script());passed(not g['controlsOut'] and g['rootWidth']==520,'Long text, dropdowns and errors do not overflow')
    await page.locator('#tabBuild').click()
    g=await page.evaluate(check_layout_script());passed(not g['controlsOut'],'Long Grafana URL does not overflow Build page')
    # Tab keyboard navigation.
    await page.locator('#tabBuild').focus();await page.keyboard.press('ArrowRight')
    passed(await page.locator('#view-results').is_visible(),'Arrow-key navigation works')
    passed(not errors,'No uncaught popup JavaScript exceptions: '+str(errors))
    await context.close();await browser.close()
    print('SMART EXPORT 2.2 POPUP SUITE PASSED')

if __name__=='__main__':asyncio.run(run())

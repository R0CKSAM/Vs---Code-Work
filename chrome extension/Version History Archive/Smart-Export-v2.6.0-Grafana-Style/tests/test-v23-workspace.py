import asyncio,base64,pathlib,importlib.util,json
from playwright.async_api import async_playwright
ROOT=pathlib.Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('se_fixture',ROOT/'tests/fixture-v22.py')
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
OUT=pathlib.Path('/mnt/data')
async def main():
  html=(ROOT/'workspace.html').read_text().replace('<link rel="stylesheet" href="workspace.css">','<style>'+ (ROOT/'workspace.css').read_text()+'</style>')
  html=html.replace('<script type="module" src="popup.mjs"></script>','').replace('<script type="module" src="workspace-nav.mjs"></script>','')
  img='data:image/png;base64,'+base64.b64encode((ROOT/'icons/icon48.png').read_bytes()).decode()
  html=html.replace('src="icons/icon48.png"',f'src="{img}"')
  async with async_playwright() as p:
   b=await p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
   for size in [(1440,900),(900,900),(600,850),(390,780)]:
    width,height=size
    c=await b.new_context(viewport={'width':width,'height':height},accept_downloads=True)
    pg=await c.new_page();errors=[];pg.on('pageerror',lambda e:errors.append(str(e)));pg.on('dialog',lambda d:asyncio.create_task(d.accept()))
    await pg.set_content(html,wait_until='domcontentloaded');await pg.add_script_tag(content=fixture.bundle())
    await pg.locator('.quick-btn').first.wait_for()
    await pg.screenshot(path=f'/mnt/data/Smart-Export-v2.3-Workspace-{width}.png',full_page=True)
    r=await pg.evaluate('''() => { const ctrls=[...document.querySelectorAll('button,input,select,a')].filter(e=>e.getClientRects().length && getComputedStyle(e).visibility!=='hidden');const out=ctrls.map(e=>({id:e.id||e.textContent.slice(0,30),r:e.getBoundingClientRect()})).filter(({r})=>r.right>innerWidth+1||r.left< -1);return {documentWidth:document.documentElement.scrollWidth,viewport:innerWidth,controlOverflow:out.map(x=>x.id),tabs:document.querySelectorAll('.page-tab').length,metrics:document.querySelectorAll('#metricCatalog .metric-item').length}}''')
    print('BASE',width,r,'errors',errors)
    assert r['documentWidth']<=width+2,('horizontal overflow',width,r)
    assert not r['controlOverflow'],('control overflow',width,r)
    assert not errors
    assert r['metrics']>=4
    if width==1440:
     await pg.locator('button[data-preset="geo"]').click()
     await pg.locator('#metricSearch').fill('playtime')
     assert await pg.locator('.metric-item').count()>=4
     await pg.locator('#clearSearch').click()
     await pg.locator('#tabResults').click();assert await pg.locator('#view-results').is_visible()
     await pg.locator('#tabBuild').click()
     await pg.locator('#dashboardUrl').fill(fixture.URL)
     await pg.locator('#dockFetch').click()
     await pg.wait_for_timeout(1020)
     assert await pg.locator('#rowCount').inner_text()=='1'
     async with pg.expect_download() as dl:await pg.locator('#downloadXlsx').click()
     d=await dl.value
     path='/mnt/data/Smart-Export-v2.3-Functional-Test.xlsx';await d.save_as(path)
     assert pathlib.Path(path).stat().st_size>2000
     await pg.screenshot(path='/mnt/data/Smart-Export-v2.3-Results-Desktop.png',full_page=True)
     await pg.locator('#tabAutomation').click();assert await pg.locator('#view-automation').is_visible()
     await pg.locator('#presetName').fill('My GEO View');await pg.locator('#savePreset').click()
     assert await pg.locator('#savedPresets').input_value()=='My GEO View'
     await pg.locator('#advancedSettings > summary').click()
     await pg.locator('#scanPanels').click();assert await pg.locator('.panel-item').count()==2
     await pg.screenshot(path='/mnt/data/Smart-Export-v2.3-Settings-Desktop.png',full_page=True)
     print('INTERACTIONS PASS')
    await c.close()
   # Tiny launcher at exact popup size
   h=(ROOT/'popup.html').read_text().replace('<link rel="stylesheet" href="launcher.css">','<style>'+ (ROOT/'launcher.css').read_text()+'</style>').replace('<script type="module" src="launcher.mjs"></script>','')
   icon='data:image/png;base64,'+base64.b64encode((ROOT/'icons/icon48.png').read_bytes()).decode();h=h.replace('src="icons/icon48.png"',f'src="{icon}"')
   c=await b.new_context(viewport={'width':356,'height':450});p2=await c.new_page();await p2.set_content(h)
   await p2.screenshot(path='/mnt/data/Smart-Export-v2.3-Launcher.png',full_page=True)
   r=await p2.evaluate('''() => ({w:document.documentElement.scrollWidth,btns:[...document.querySelectorAll('button')].map(x=>x.getBoundingClientRect().right)})''')
   assert r['w']==356 and max(r['btns'])<=356
   await c.close();await b.close()
   print('WORKSPACE UI PASS')
asyncio.run(main())

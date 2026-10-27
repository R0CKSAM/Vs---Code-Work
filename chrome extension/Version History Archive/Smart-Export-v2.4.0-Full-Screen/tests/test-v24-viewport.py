import asyncio,base64,pathlib,importlib.util,json
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
ROOT=pathlib.Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('se_fixture',ROOT/'tests/fixture-v22.py')
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
OUT=pathlib.Path('/mnt/data')

def html():
 s=BeautifulSoup((ROOT/'workspace.html').read_text(),'html.parser')
 for link in s.select('link[href="workspace.css"]'):
  style=s.new_tag('style');style.string=(ROOT/'workspace.css').read_text();link.replace_with(style)
 for script in s.select('script[src]'):script.decompose()
 for img in s.select('img[src="icons/icon48.png"]'):
  img['src']='data:image/png;base64,'+base64.b64encode((ROOT/'icons/icon48.png').read_bytes()).decode()
 return str(s)

async def main():
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
  for w,h in [(1920,1080),(1440,900),(1366,768),(1024,768),(768,900),(390,844)]:
   ctx=await browser.new_context(viewport={'width':w,'height':h},accept_downloads=True)
   pg=await ctx.new_page();errors=[];pg.on('pageerror',lambda e:errors.append(str(e)));pg.on('dialog',lambda d:asyncio.create_task(d.accept()))
   await pg.set_content(html(),wait_until='domcontentloaded');await pg.add_script_tag(content=fixture.bundle());await pg.locator('.quick-btn').first.wait_for()
   await pg.wait_for_timeout(180)
   dims=await pg.evaluate('''() => {
    const v=document.querySelector('#view-build').getBoundingClientRect();
    const shell=document.querySelector('.shell').getBoundingClientRect();
    const dock=document.querySelector('.dock').getBoundingClientRect();
    const sidebar=document.querySelector('.sidebar').getBoundingClientRect();
    const metric=document.querySelector('.metric-list').getBoundingClientRect();
    const shown=[...document.querySelectorAll('button,input,select')].filter(x=>{let a=x.getBoundingClientRect();return a.width>0&&a.height>0&&getComputedStyle(x).visibility!=='hidden'});
    const overlaps=shown.filter(x=>{let a=x.getBoundingClientRect();return a.left<-2||a.right>innerWidth+2;}).map(x=>x.id||x.textContent.slice(0,20));
    return {width:document.documentElement.scrollWidth, height:document.documentElement.scrollHeight,viewport:[innerWidth,innerHeight],shell:[shell.width,shell.height],view:[v.y,v.height],dock:[dock.y,dock.bottom],sidebar:[sidebar.x,sidebar.width],metric:[metric.y,metric.height],overlaps,bodyOverflow:getComputedStyle(document.body).overflowY};
   }''')
   print('BUILD',w,h,dims,'errors',errors)
   assert dims['width']<=w+2,(w,dims)
   assert dims['height']<=h+2,(h,dims)
   assert not dims['overlaps'],(w,dims)
   assert dims['dock'][1] <= h+2,(w,dims)
   assert not errors,(w,errors)
   await pg.screenshot(path=str(OUT/f'Smart-Export-v2.4-Workspace-{w}.png'))
   # Core navigation and forms
   await pg.locator('#tabResults').click()
   await pg.locator('#view-results').wait_for(state='visible')
   assert await pg.locator('#previewEmpty').is_visible()
   await pg.locator('#tabAutomation').click();assert await pg.locator('#view-automation').is_visible()
   await pg.locator('#advancedSettings > summary').click()
   await pg.locator('#presetName').fill('Automated test view')
   await pg.locator('#savePreset').click()
   await pg.locator('#savedPresets').select_option('Automated test view')
   # test dropdown arrow safe and no collision
   dropdown=await pg.locator('#savedPresets').bounding_box();chevron=await pg.locator('#savedPresets + .chevron').bounding_box()
   if chevron:
    assert dropdown['x']<=chevron['x'] and chevron['x']+chevron['width']<dropdown['x']+dropdown['width'],(dropdown,chevron)
   await pg.screenshot(path=str(OUT/f'Smart-Export-v2.4-Settings-{w}.png'))
   await pg.locator('#tabBuild').click()
   await pg.locator('button[data-preset="geo"]').click()
   await pg.locator('#dashboardUrl').fill(fixture.URL)
   await pg.locator('#dockFetch').click()
   await pg.wait_for_timeout(850)
   await pg.locator('#tabResults').click()
   assert await pg.locator('#rowCount').inner_text()=='1',(w,await pg.locator('#rowCount').inner_text())
   assert await pg.locator('#downloadXlsx').is_enabled()
   if w==1440:
    async with pg.expect_download() as download_event:await pg.locator('#downloadXlsx').click()
    download=await download_event.value;await download.save_as(str(OUT/'Smart-Export-v2.4-Test.xlsx'))
   await pg.screenshot(path=str(OUT/f'Smart-Export-v2.4-Results-{w}.png'))
   assert not errors,errors
   await ctx.close()
  await browser.close()
 print('PASS 6 viewport sizes, navigation, saved view, dropdown, Excel enablement')

asyncio.run(main())

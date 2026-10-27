import asyncio,pathlib,base64,importlib.util
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
ROOT=pathlib.Path(__file__).resolve().parent.parent
sp=importlib.util.spec_from_file_location('fix',ROOT/'tests/fixture-v22.py');fix=importlib.util.module_from_spec(sp);sp.loader.exec_module(fix)
s=BeautifulSoup((ROOT/'workspace.html').read_text(),'html.parser')
for link in s.select('link[href="workspace.css"]'):
 st=s.new_tag('style');st.string=(ROOT/'workspace.css').read_text();link.replace_with(st)
for t in s.select('script[src]'):t.decompose()
for img in s.select('img[src="icons/icon48.png"]'):
 img['src']='data:image/png;base64,'+base64.b64encode((ROOT/'icons/icon48.png').read_bytes()).decode()
async def main():
 async with async_playwright() as p:
  b=await p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
  for width,height in [(1920,1080),(1366,768),(1024,768),(768,900),(390,844)]:
   ctx=await b.new_context(viewport={'width':width,'height':height},accept_downloads=True)
   pg=await ctx.new_page();errors=[];pg.on('pageerror',lambda e:errors.append(str(e)));pg.on('dialog',lambda d:asyncio.create_task(d.accept()))
   await pg.set_content(str(s));await pg.add_script_tag(content=fix.bundle())
   await pg.locator('.quick-btn').first.wait_for()
   await pg.locator('#moreTemplates').click();await pg.locator('button[data-preset="all"]').click()
   assert (await pg.locator('#selectedCount').inner_text())=='21 metrics'
   await pg.locator('#metricSearch').fill('session');await pg.locator('#clearSearch').click()
   await pg.locator('#dashboardUrl').fill('https://grafana-apj.trafficpeak.live/d/db7ce6f6-d689-4976-89e5-ddf0b5401f97/dash?orgId=743&from=now-7d&to=now'+'&xx='+'A'*850)
   await pg.locator('#tabAutomation').click()
   await pg.locator('#advancedSettings > summary').click()
   await pg.locator('#presetName').fill('z'*40);await pg.locator('#savePreset').click()
   await pg.locator('#savedPresets').select_option('z'*40)
   await pg.locator('#feedback').evaluate('(el)=>{el.textContent="ERR-"+"Q".repeat(5000);el.closest(".feedback-wrap").dataset.kind="error"}')
   await pg.screenshot(path=f'/mnt/data/Smart-Export-v2.4-Stress-{width}.png')
   r=await pg.evaluate('''() => ({
      w:document.documentElement.scrollWidth,h:document.documentElement.scrollHeight,
      panel:document.querySelector('#view-automation').getBoundingClientRect().width,
      controls:[...document.querySelectorAll('button,input,select')].filter(x=>{const r=x.getBoundingClientRect();return r.width>0&&r.height>0&&(r.right>innerWidth+1||r.left< -1)}).map(x=>x.id||x.textContent.slice(0,30)),
      allSelected:document.querySelector('#selectedCount').textContent,
      dockBottom:document.querySelector('.dock').getBoundingClientRect().bottom,
      settingsOpen:document.querySelector('#advancedSettings').open
   })''')
   assert r['w']<=width+2 and r['h']<=height+2,(width,r)
   assert not r['controls'],(width,r)
   assert abs(r['dockBottom']-height)<2,(width,r)
   assert r['settingsOpen'] and r['allSelected']=='21 metrics',(width,r)
   assert not errors,(width,errors)
   print('STRESS',width,height,'PASS')
   await ctx.close()
  await b.close()
 print('PASS 5 stress layouts, 21 metrics, long source, huge error, expanded settings')
asyncio.run(main())

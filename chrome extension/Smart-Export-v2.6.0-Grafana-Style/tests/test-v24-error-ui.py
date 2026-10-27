import asyncio,base64,importlib.util,pathlib
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
ROOT=pathlib.Path(__file__).resolve().parent.parent
sp=importlib.util.spec_from_file_location('fixture',ROOT/'tests/fixture-v22.py');f=importlib.util.module_from_spec(sp);sp.loader.exec_module(f)
s=BeautifulSoup((ROOT/'workspace.html').read_text(),'html.parser')
for l in s.select('link[href="workspace.css"]'):
 st=s.new_tag('style');st.string=(ROOT/'workspace.css').read_text();l.replace_with(st)
for t in s.select('script[src]'):t.decompose()
for x in s.select('img[src="icons/icon48.png"]'):
 x['src']='data:image/png;base64,'+base64.b64encode((ROOT/'icons/icon48.png').read_bytes()).decode()
async def main():
 async with async_playwright() as p:
  b=await p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
  c=await b.new_context(viewport={'width':1280,'height':720})
  pg=await c.new_page();errs=[];pg.on('pageerror',lambda e:errs.append(str(e)))
  await pg.set_content(str(s));await pg.add_script_tag(content=f.bundle())
  await pg.locator('.quick-btn').first.wait_for()
  await pg.locator('#dashboardUrl').fill(f.URL)
  await pg.evaluate('''() => { const orig=chrome.runtime.sendMessage;chrome.runtime.sendMessage=(msg,cb)=>{if(msg.type==='SYNC_PICKED')return cb({ok:false,error:'Conflicting content data for date=2026-10-01, content_title=India TV: unique_ips differed between Grafana frames. Nothing was saved.'});return orig(msg,cb)};}''')
  await pg.locator('#dockFetch').click()
  await pg.locator('#feedbackHelp').wait_for(state='visible')
  assert 'Conflicting content data' in await pg.locator('#feedback').inner_text()
  await pg.locator('#feedbackHelp').click()
  assert await pg.locator('#view-automation').is_visible()
  assert await pg.locator('#advancedSettings').get_attribute('open') is not None
  assert await pg.locator('#logs').is_visible()
  await pg.locator('#feedbackDismiss').click()
  assert await pg.locator('#feedbackHelp').is_hidden()
  assert not errs,errs
  await b.close()
 print('PASS error message -> troubleshooting -> logs; dismiss and no UI errors')
asyncio.run(main())

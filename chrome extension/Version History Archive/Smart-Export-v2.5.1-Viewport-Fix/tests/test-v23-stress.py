import asyncio,base64,pathlib,importlib.util
from playwright.async_api import async_playwright
ROOT=pathlib.Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('fixture',ROOT/'tests/fixture-v22.py')
f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
async def main():
 html=(ROOT/'workspace.html').read_text().replace('<link rel="stylesheet" href="workspace.css">','<style>'+ (ROOT/'workspace.css').read_text()+'</style>')
 html=html.replace('<script type="module" src="popup.mjs"></script>','').replace('<script type="module" src="workspace-nav.mjs"></script>','')
 icon='data:image/png;base64,'+base64.b64encode((ROOT/'icons/icon48.png').read_bytes()).decode();html=html.replace('src="icons/icon48.png"',f'src="{icon}"')
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
  for width in [1440,900,600,390]:
   c=await browser.new_context(viewport={'width':width,'height':800});pg=await c.new_page();errs=[];pg.on('pageerror',lambda e:errs.append(str(e)))
   await pg.set_content(html);await pg.add_script_tag(content=f.bundle());await pg.locator('.quick-btn').first.wait_for()
   await pg.locator('#moreTemplates').click();await pg.locator('button[data-preset="all"]').click()
   assert await pg.locator('#selectedCount').inner_text()=='21 metrics'
   await pg.locator('#dashboardUrl').fill(f.URL+'q'*850)
   await pg.locator('#tabAutomation').click()
   await pg.locator('#presetName').fill('x'*40)
   await pg.locator('#savePreset').click()
   await pg.locator('#advancedSettings > summary').click()
   await pg.locator('#feedback').evaluate('(e)=>e.textContent="LONG_ERROR_"+"Z".repeat(6000)')
   dims=await pg.evaluate('''()=>({w:document.documentElement.scrollWidth,controls:[...document.querySelectorAll('button,input,select')].filter(e=>e.getClientRects().length).filter(e=>{const r=e.getBoundingClientRect();return r.right>innerWidth+2||r.left< -2}).map(e=>e.id||e.textContent.slice(0,20))})''')
   assert dims['w']<=width+1,(width,dims)
   assert not dims['controls'],(width,dims)
   assert not errs,(width,errs)
   await pg.locator('#tabBuild').click()
   dims=await pg.evaluate('document.documentElement.scrollWidth')
   assert dims<=width+1,(width,dims)
   await c.close()
  await browser.close()
 print('PASS: 21 selected metrics, expanded settings, long URLs, saved views, long errors at 1440/900/600/390 px')
asyncio.run(main())

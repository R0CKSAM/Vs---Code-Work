import asyncio, pathlib, re, base64
from playwright.async_api import async_playwright
DIR=pathlib.Path(__file__).resolve().parent.parent
async def main():
 html=(DIR/'popup.html').read_text()
 css=(DIR/'popup.css').read_text()
 html=html.replace('<link href="popup.css" rel="stylesheet">','<style>'+css+'</style>')
 html=re.sub(r'<script type="module" src="popup.mjs"></script>','',html)
 image=base64.b64encode((DIR/'icons/icon48.png').read_bytes()).decode()
 html=html.replace('src="icons/icon48.png"','src="data:image/png;base64,'+image+'"')
 async with async_playwright() as p:
  browser=await p.chromium.launch(headless=True, executable_path='/usr/bin/chromium', args=['--no-sandbox'])
  pg=await browser.new_page(viewport={'width':540,'height':650},device_scale_factor=2)
  await pg.set_content(html)
  await pg.evaluate('''() => {document.querySelector('#rowCount').textContent='12,450';document.querySelector('#dayCount').textContent='30';document.querySelector('#rangeDetails').textContent='2026-09-25 to 2026-10-25 · Master stored locally';document.querySelector('#stateChip').textContent='DAILY ON';document.querySelector('#autoDaily').checked=true;document.querySelector('#dashboardUrl').value='https://grafana-apj.trafficpeak.live/d/db7ce6f6-d689-4976-89e5-ddf0b5401f97/sessions-users-monitoring?orgId=743&from=2026-10-01&to=2026-10-30&var-filter=';document.querySelector('#lastSynced').textContent='Last successful sync: 26 October 2026 · Daily update ON';}''')
  stats=await pg.evaluate('''() => ({width:document.documentElement.scrollWidth,bodyWidth:document.body.scrollWidth,buttons:[...document.querySelectorAll('button')].map(b=>({id:b.id, r:b.getBoundingClientRect().toJSON()}))})''')
  print('Popup width',stats['width'],stats['bodyWidth'])
  assert stats['width']==540 and stats['bodyWidth']==540
  for item in stats['buttons']:
   r=item['r'];assert r['x']>=-0.1 and r['right']<=540.1 and r['height']>=32,(item['id'],r)
  await pg.add_style_tag(content='html,body{height:auto!important;max-height:none!important;overflow-y:visible!important}.shell{height:auto!important}')
  await pg.screenshot(path='/mnt/data/Smart-Export-v1-UI-Full.png',full_page=True)
  await pg.locator('details.advanced summary').click()
  details=await pg.evaluate('''() => ({width:document.documentElement.scrollWidth, cards:[...document.querySelectorAll('.card')].map(e=>e.getBoundingClientRect().toJSON()),buttons:[...document.querySelectorAll('button')].map(e=>e.getBoundingClientRect().toJSON())})''')
  assert details['width']==540
  assert all(r['left']>=0 and r['right']<=540.1 for r in details['cards']+details['buttons'])
  print('UI test passed: visible and expanded states; no horizontal overflow/bleeding, correct button sizes.')
  await browser.close()
asyncio.run(main())

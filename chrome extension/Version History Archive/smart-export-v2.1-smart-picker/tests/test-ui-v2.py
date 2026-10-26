import asyncio,pathlib,re
from playwright.async_api import async_playwright
ROOT=pathlib.Path('/mnt/data/smart-export-v2')
async def main():
 html=(ROOT/'popup.html').read_text()
 css=(ROOT/'popup.css').read_text()
 html=html.replace('<link rel="stylesheet" href="popup.css">',f'<style>{css}</style>')
 html=html.replace('<script type="module" src="popup.mjs"></script>','')
 # Broken images outside an extension context have no bearing on layout constraints.
 html=html.replace('src="icons/icon48.png"','src="data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' width=\'48\' height=\'48\'%3E%3Crect width=\'48\' height=\'48\' fill=\'%230d3e50\'/%3E%3Ctext x=\'12\' y=\'32\' fill=\'%238ff8e4\'%3EX%3C/text%3E%3C/svg%3E"')
 async with async_playwright() as p:
  browser=await p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  page=await browser.new_page(viewport={'width':450,'height':585})
  await page.set_content(html)
  await page.evaluate('''() => {document.querySelector('#rowCount').textContent='22,451';document.querySelector('#dayCount').textContent='30';document.querySelector('#variantCount').innerHTML='6<span class="slash">/6</span>';document.querySelector('#rangeDetails').textContent='Stored history: 2026-10-01 to 2026-10-25';document.querySelector('#stateChip').textContent='DAILY ON';}''')
  await page.screenshot(path='/mnt/data/Smart-Export-v2-UI-Preview.png')
  d=await page.evaluate('''() => {let x=document.querySelector('#reportType').getBoundingClientRect(),y=document.querySelector('.select-arrow').getBoundingClientRect();return {scrollWidth:document.documentElement.scrollWidth,width:document.documentElement.clientWidth,body:document.body.getBoundingClientRect().width,centerGap:Math.abs((x.top+x.bottom)/2-(y.top+y.bottom)/2),arrowRight:x.right-y.right}}''')
  print('default',d)
  assert d['scrollWidth']<=d['width'] and d['body']==450 and d['centerGap']<8 and d['arrowRight']>5
  await page.locator('details.advanced summary').click()
  await page.evaluate('''() => {document.querySelector('#dashboardUrl').value='https://grafana-apj.trafficpeak.live/'+ 'Y'.repeat(600);let f=document.querySelector('#feedback');f.textContent='A_LONG_ERROR_WITHOUT_SPACES_'+'X'.repeat(800);f.classList.add('error');document.querySelector('#reportType').value='devices';}''')
  await page.screenshot(path='/mnt/data/Smart-Export-v2-Expanded-Preview.png')
  d=await page.evaluate('''() => ({full:document.documentElement.scrollWidth,client:document.documentElement.clientWidth,main:document.querySelector('main').scrollWidth,mainClient:document.querySelector('main').clientWidth,feedback:document.querySelector('#feedback').scrollWidth,feedbackClient:document.querySelector('#feedback').clientWidth})''')
  print('stress',d)
  assert d['full']<=d['client'] and d['main']<=d['mainClient'] and d['feedback']<=d['feedbackClient']
  await page.set_viewport_size({'width':360,'height':585})
  n=await page.evaluate('''() => ({full:document.documentElement.scrollWidth,client:document.documentElement.clientWidth})''')
  print('narrow',n)
  assert n['full']<=n['client']
  print('UI geometry PASS')
  await browser.close()
asyncio.run(main())

import asyncio, re, json, tempfile, pathlib, os
from playwright.async_api import async_playwright
UID='db7ce6f6-d689-4976-89e5-ddf0b5401f97'
ORIGIN='https://grafana-apj.trafficpeak.live'
DIR='/mnt/data/smart-export-v1'
MOCK_ROWS=[
 ['2026-10-01','2026-10-02','2026-10-03'],
 ['IN','IN','IN'],
 ['Delhi','Maharashtra','Delhi'],
 ['NEWDELHI','MUMBAI','NEWDELHI'],
 [100.2,125.5,130.1]
]
API_SQL="SELECT count() * 6 / 60.0 as playtime_hours FROM ${table} WHERE reqPath LIKE '%.ts'"
async def main():
 async with async_playwright() as p:
  userdata=tempfile.mkdtemp(prefix='smart-export-qa-')
  ctx=await p.chromium.launch_persistent_context(userdata,headless=True,executable_path='/usr/bin/chromium',
    args=['--no-sandbox',f'--disable-extensions-except={DIR}',f'--load-extension={DIR}'],accept_downloads=True,viewport={'width':540,'height':700})
  try:
   sw=ctx.service_workers[0] if ctx.service_workers else await ctx.wait_for_event('serviceworker',timeout=30000)
   print('worker:',sw.url)
   mid=re.search(r'chrome-extension://([a-z]+)/',sw.url)
   assert mid,sw.url
   eid=mid.group(1)
   page=await ctx.new_page()
   seen=[]
   async def route_handler(route):
    url=route.request.url
    if '/api/dashboards/uid/' in url:
     dash={'dashboard':{'uid':UID,'panels':[{'id':20,'title':'Playtime by GEO','targets':[{'rawSql':API_SQL,'datasource':{'type':'hydrolix-hydrolix-datasource','uid':'mockds'}}]}]}}
     return await route.fulfill(status=200,content_type='application/json',body=json.dumps(dash))
    if '/api/ds/query' in url:
     try:payload=route.request.post_data_json
     except:payload={}
     seen.append(payload)
     return await route.fulfill(status=200,content_type='application/json',body=json.dumps({'results':{'A':{'frames':[{'schema':{'fields':[{'name':x} for x in ['report_date','country','state','city','playtime_minutes']]},'data':{'values':MOCK_ROWS}}]}}}))
    return await route.fulfill(status=200,content_type='text/html',body='<html><body>Authenticated Grafana simulation</body></html>')
   await page.route(f'{ORIGIN}/**',route_handler)
   await page.goto(f'{ORIGIN}/d/{UID}/sessions-users-monitoring?orgId=743&var-filter=',wait_until='domcontentloaded')
   pop=await ctx.new_page()
   await pop.goto(f'chrome-extension://{eid}/popup.html',wait_until='domcontentloaded')
   await pop.wait_for_timeout(500)
   assert await pop.title()=='Smart Export'
   assert await pop.locator('h1').count()==1
   await pop.locator('#dateFrom').fill('2026-10-01')
   await pop.locator('#dateTo').fill('2026-10-03')
   await pop.locator('#syncNow').click()
   await pop.wait_for_function("document.querySelector('#rowCount').textContent==='3'",timeout=20000)
   print('SYNC: 3 rows, days:',await pop.locator('#dayCount').inner_text(), 'requests',len(seen))
   assert len(seen)==1
   assert seen[0]['queries'][0]['datasource']['uid']=='mockds'
   async with pop.expect_download() as d:
    await pop.locator('#downloadXlsx').click()
   download=await d.value
   print('XLSX filename:',download.suggested_filename)
   assert download.suggested_filename.endswith('.xlsx')
   await download.save_as('/mnt/data/smart-export-v1/tests/browser-export.xlsx')
   async with pop.expect_download() as d:
    await pop.locator('#downloadCsv').click()
   csv=await d.value
   await csv.save_as('/mnt/data/smart-export-v1/tests/browser-export.csv')
   print('CSV filename:',csv.suggested_filename)
   # Re-fetch same window: rows should replace, not duplicate
   await pop.locator('#syncNow').click()
   await pop.wait_for_timeout(700)
   assert await pop.locator('#rowCount').inner_text()=='3'
   print('Dedup/overwrite test passed, requests:',len(seen))
   # Screenshot of actual popup after refreshing
   await pop.screenshot(path='/mnt/data/Smart-Export-v1-UI.png',full_page=True)
   await pop.locator('details.advanced summary').click()
   spill=await pop.evaluate('''() => ({w:document.documentElement.scrollWidth,body:document.body.scrollWidth,inputs:[...document.querySelectorAll('input')].map(e=>({name:e.id,w:e.getBoundingClientRect().width})), cards:[...document.querySelectorAll('.card')].map(e=>({w:e.getBoundingClientRect().width,left:e.getBoundingClientRect().left,right:e.getBoundingClientRect().right}))})''')
   print('LAYOUT:',spill)
   assert spill['w']<=540 and spill['body']<=540
   assert all(0<=x['left']<=x['right']<=540 for x in spill['cards'])
   print('BROWSER E2E PASS')
  finally:
   await ctx.close()
asyncio.run(main())

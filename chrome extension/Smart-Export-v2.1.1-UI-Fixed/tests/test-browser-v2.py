import asyncio,re,json,tempfile,os,pathlib,zipfile
from playwright.async_api import async_playwright
ROOT='/mnt/data/smart-export-v2';ORIGIN='https://grafana-apj.trafficpeak.live';UID='db7ce6f6-d689-4976-89e5-ddf0b5401f97'
DOC=json.load(open('/mnt/data/Pasted text(20261019-055636).txt'))
F={
'kpis':dict(report_date=['2026-10-01','2026-10-02'],unique_devices=[20,25],unique_ips=[15,16],session_ids=[45,55],ip_ua_sessions=[33,44],manifest_views=[70,80],playtime_minutes=[155,166],bandwidth_bytes=[123456,145678]),
'channel':dict(report_date=['2026-10-01','2026-10-02'],channel_name=['News','Cricket'],playtime_minutes=[50,75],unique_ips=[15,22]),
'geo':dict(report_date=['2026-10-01','2026-10-02'],country=['IN','IN'],state=['Delhi','Maharashtra'],city=['New Delhi','Mumbai'],playtime_minutes=[45,87]),
'devices':dict(report_date=['2026-10-01','2026-10-02'],platform=['Samsung Smart TV','Fire TV'],operating_system=['Tizen','FireOS'],unique_devices=[12,15],unique_ips=[13,18]),
'content':dict(report_date=['2026-10-01','2026-10-02'],content_title=['Episode%201','Episode%202'],manifest_views=[80,90],unique_ips=[40,49],unique_devices=[38,40],session_ids=[55,58]),
'traffic':dict(report_date=['2026-10-01','2026-10-02'],hour_ist=['2026-10-01 12:00','2026-10-02 13:00'],unique_ips=[22,30],session_ids=[45,55],manifest_views=[57,62],playtime_minutes=[81,95],bandwidth_bytes=[11567,15900])
}
def recognize(sql):
 if 'AS operating_system' in sql:return 'devices'
 if 'AS content_title' in sql:return 'content'
 if 'AS hour_ist' in sql:return 'traffic'
 if 'AS channel_name' in sql or 'channel_name,' in sql:return 'channel'
 if 'AS country' in sql:return 'geo'
 if 'AS unique_devices' in sql:return 'kpis'
 raise Exception('Unrecognized SQL '+sql[:200])
async def main():
 seen=[];userdir=tempfile.mkdtemp(prefix='smart-export-v2-check-')
 async with async_playwright() as p:
  ctx=await p.chromium.launch_persistent_context(userdir,headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox',f'--disable-extensions-except={ROOT}',f'--load-extension={ROOT}'],accept_downloads=True,viewport={'width':700,'height':800})
  try:
   sw=ctx.service_workers[0] if ctx.service_workers else await ctx.wait_for_event('serviceworker',timeout=20000)
   eid=re.search(r'chrome-extension://([a-z]+)/',sw.url).group(1);print('ID',eid)
   page=await ctx.new_page()
   async def handler(route):
    url=route.request.url
    if '/api/dashboards/uid/' in url:
     return await route.fulfill(status=200,content_type='application/json',body=json.dumps({'dashboard':DOC}))
    if '/api/ds/query' in url:
     data=route.request.post_data_json
     sql=data['queries'][0]['rawSql']
     typ=recognize(sql);seen.append(typ)
     cols=F[typ]
     out={'results':{'A':{'frames':[{'schema':{'fields':[{'name':x} for x in cols]},'data':{'values':list(cols.values())}}]}}}
     return await route.fulfill(status=200,content_type='application/json',body=json.dumps(out))
    return await route.fulfill(status=200,content_type='text/html',body='<html><body>Grafana signed-in mock</body></html>')
   await page.route(f'{ORIGIN}/**',handler)
   await page.goto(f'{ORIGIN}/d/{UID}/sessions-users-monitoring?orgId=743&var-filter=',wait_until='domcontentloaded')
   pop=await ctx.new_page();await pop.goto(f'chrome-extension://{eid}/popup.html',wait_until='domcontentloaded')
   await pop.wait_for_timeout(500)
   print('TITLE',await pop.title(),'report',await pop.locator('#reportType').input_value())
   assert await pop.locator('#reportType').input_value()=='executive'
   await pop.locator('#dateFrom').fill('2026-10-01');await pop.locator('#dateTo').fill('2026-10-02');
   await pop.locator('#syncNow').click();await pop.wait_for_function("document.querySelector('#rowCount').textContent==='12'",timeout=40000)
   print('seen',seen,'records',await pop.locator('#rowCount').inner_text(),'status',await pop.locator('#feedback').inner_text())
   assert set(seen)==set(F)
   assert await pop.locator('#variantCount').inner_text()=='6/6'
   await pop.wait_for_timeout(100)
   print('horizontal overflow?',await pop.evaluate('document.documentElement.scrollWidth > document.documentElement.clientWidth'))
   assert not await pop.evaluate('document.documentElement.scrollWidth > document.documentElement.clientWidth')
   os.makedirs('/mnt/data/smart-export-v2/tests',exist_ok=True)
   await pop.screenshot(path='/mnt/data/Smart-Export-v2-UI-Preview.png',full_page=True)
   async with pop.expect_download(timeout=20000) as ticket:await pop.locator('#downloadXlsx').click()
   dl=await ticket.value
   print('Excel file:',dl.suggested_filename)
   path='/mnt/data/smart-export-v2/tests/browser-master.xlsx';await dl.save_as(path)
   with zipfile.ZipFile(path) as z:assert len([x for x in z.namelist() if x.startswith('xl/worksheets/sheet')])==7
   await pop.locator('#reportType').select_option('geo');await pop.wait_for_timeout(350)
   async with pop.expect_download() as ticket:await pop.locator('#downloadCsv').click()
   await (await ticket.value).save_as('/mnt/data/smart-export-v2/tests/browser-geo.csv')
   await pop.locator('details.advanced summary').click();await pop.screenshot(path='/mnt/data/Smart-Export-v2-UI-Expanded.png',full_page=True)
   # Re-run GEO; its master must replace, not duplicate.
   await pop.locator('#syncNow').click();await pop.wait_for_timeout(500)
   assert await pop.locator('#rowCount').inner_text()=='2'
   print('Browser extension test PASS; requests',len(seen))
  finally: await ctx.close()
asyncio.run(main())

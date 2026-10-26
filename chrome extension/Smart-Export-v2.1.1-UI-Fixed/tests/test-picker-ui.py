import asyncio, pathlib, re, base64
from playwright.async_api import async_playwright
ROOT=pathlib.Path(__file__).resolve().parent.parent
MODS=['core.mjs','reports.mjs','metric-catalog.mjs','report-db.mjs','multi-xlsx.mjs','picked-export.mjs','popup.mjs']
MOCK="""const CONFIG_URL='https://grafana-apj.trafficpeak.live/d/db7ce6f6-d689-4976-89e5-ddf0b5401f97/sessions-users-monitoring?orgId=743&from=now-7d&to=now&timezone=Asia%2FKolkata&var-filter=';
const data={};
window.chrome={runtime:{lastError:null,getURL:(p)=>'chrome-extension://testextensionid/'+p,sendMessage:(req,cb)=>{
 if(req.type==='STATE_V2')cb({ok:true,data:{config:{dashboardUrl:CONFIG_URL,enabled:false,lastSuccessAt:null,autoReport:'geo'},summaries:Object.fromEntries(['kpis','channel','geo','devices','content','traffic'].map(k=>[k,{rows:0,days:0}])),coverage:{uniqueDays:0},busy:false}});
 else if(req.type==='CURRENT_GRAFANA_TAB')cb({ok:true,data:{url:CONFIG_URL}});
 else cb({ok:true,data:{config:{dashboardUrl:CONFIG_URL,enabled:false}}});
}},storage:{local:{get:async defaults=>({...defaults,...data}),set:async x=>Object.assign(data,x)},onChanged:{addListener:()=>{}}},tabs:{create:()=>{}}};
"""
def bundle():
 pieces=[MOCK,'const __modules={};']
 for name in MODS:
  if name=='report-db.mjs':
   pieces.append("__modules['report-db.mjs']={allReportRows:async()=>Object.fromEntries(['kpis','channel','geo','devices','content','traffic'].map(k=>[k,[]]))};")
   continue
  s=(ROOT/name).read_text()
  imports=[]
  def remove(m):
   names,source=m.group(1),m.group(2)
   imports.append(f"const {{{names}}}=__modules[{source!r}];")
   return ''
  s=re.sub(r"^import\s+\{(.*?)\}\s+from\s+['\"]\./([^'\"]+)['\"];?\s*$",lambda m: remove_import(m,imports),s,flags=re.M)
  exports=set(re.findall(r'^export\s+(?:(?:async)\s+)?(?:const|function|class)\s+(\w+)',s,flags=re.M))
  for t in re.findall(r'^export\s*\{(.*?)\};?\s*$',s,flags=re.M):
   exports.update(x.strip() for x in t.split(','))
  s=re.sub(r'^export\s*\{.*?\};?\s*$', '',s,flags=re.M)
  s=re.sub(r'^export\s+(?=(?:async\s+)?(?:const|function|class)\s+)', '',s,flags=re.M)
  if name!='popup.mjs':
   pieces.append(f"__modules[{name!r}]=(()=>{{\n"+'\n'.join(imports)+'\n'+s+'\nreturn {'+','.join(sorted(exports))+'};\n})();')
  else:
   pieces.append('(()=>{\n'+'\n'.join(imports)+'\n'+s+'\n})();')
 return '\n'.join(pieces)

def remove_import(m,imports):
 names,source=m.group(1),m.group(2)
 imports.append(f"const {{{names}}}=__modules[{source!r}];")
 return ''
async def inspect(page):
 return await page.evaluate('''() => {const m=document.querySelector('main'),catalog=document.querySelector('#metricCatalog');return {root:document.documentElement.scrollWidth,body:document.body.clientWidth,mainScroll:m.scrollWidth,mainClient:m.clientWidth,catalogScroll:catalog.scrollWidth,catalogClient:catalog.clientWidth,badBtns:[...document.querySelectorAll('button')].filter(x=>{let r=x.getBoundingClientRect();return r.right>522||r.left<-1}).map(x=>x.id||x.textContent.trim().slice(0,18)),count:document.querySelector('#selectedCount').textContent}}''')
async def main():
 html=(ROOT/'popup.html').read_text();css=(ROOT/'popup.css').read_text()
 html=html.replace('<link rel="stylesheet" href="popup.css">','<style>'+css+'</style>').replace('<script type="module" src="popup.mjs"></script>','')
 logo='data:image/png;base64,'+base64.b64encode((ROOT/'icons/icon48.png').read_bytes()).decode()
 html=html.replace('src="icons/icon48.png"',f'src="{logo}"')
 async with async_playwright() as p:
  browser=await p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  page=await browser.new_page(viewport={'width':520,'height':590},device_scale_factor=1)
  errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  await page.set_content(html,wait_until='domcontentloaded')
  await page.add_script_tag(content=bundle())
  await page.locator('#metricCatalog input[type=checkbox]').first.wait_for()
  await page.screenshot(path='/mnt/data/Smart-Export-v2.1-UI-Preview.png')
  d=await inspect(page);print('default',d)
  assert d['root']==520 and d['mainScroll']<=d['mainClient'] and not d['badBtns']
  await page.locator('#metricSearch').fill('playtime')
  assert await page.locator('.metric-category').count()>=3
  await page.locator('#clearSearch').click()
  await page.locator('button[data-preset="channel"]').click()
  visible=await page.locator('#exportFilterBox').is_visible()
  assert visible, 'Single category should expose dimension filter'
  align=await page.evaluate("""() => {let a=document.querySelector('#filterField').getBoundingClientRect(),b=document.querySelector('#exportFilterBox .chevron').getBoundingClientRect();return {vertical:Math.abs((a.top+a.bottom)/2-(b.top+b.bottom)/2),right:a.right-b.right}}""")
  print('filter arrow alignment',align);assert align['vertical']<8 and align['right']>6
  await page.locator('button[data-preset="all"]').click()
  await page.locator('#automationSettings summary').click()
  await page.locator('#advancedSettings summary').click()
  await page.locator('#dashboardUrl').fill('https://grafana-apj.trafficpeak.live/d/'+'Y'*600)
  await page.locator('#feedback').evaluate('(el)=>el.textContent="ERROR_"+"X".repeat(900)')
  await page.screenshot(path='/mnt/data/Smart-Export-v2.1-Expanded-Preview.png')
  st=await inspect(page);print('stress',st)
  assert st['root']==520 and st['mainScroll']<=st['mainClient'] and st['catalogScroll']<=st['catalogClient'] and not st['badBtns']
  assert await page.locator('#selectedCount').inner_text() == '21 metrics'
  print('page errors', errors); assert not errors
  print('UI STRESS PASSED')
  await browser.close()
asyncio.run(main())

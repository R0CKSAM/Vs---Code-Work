"""Full UI sanity suite for Smart Export v2.1.1.
Uses actual popup.html/CSS/JS with mocked Chrome bridge and Grafana sample rows.
No authenticated/live Grafana requests. Tests visible functionality and downloads.
"""
import asyncio, base64, pathlib, re, json, sys
from playwright.async_api import async_playwright
ROOT=pathlib.Path(__file__).resolve().parent.parent
MODS=['core.mjs','reports.mjs','metric-catalog.mjs','report-db.mjs','multi-xlsx.mjs','picked-export.mjs','popup.mjs']
URL='https://grafana-apj.trafficpeak.live/d/db7ce6f6-d689-4976-89e5-ddf0b5401f97/sessions-users-monitoring?orgId=743&from=now-7d&to=now&timezone=Asia%2FKolkata&var-filter='
MOCK=r'''const CONFIG_URL='https://grafana-apj.trafficpeak.live/d/db7ce6f6-d689-4976-89e5-ddf0b5401f97/sessions-users-monitoring?orgId=743&from=now-7d&to=now&timezone=Asia%2FKolkata&var-filter=';
window.TEST_MOCK={rows:{},state:{dashboardUrl:CONFIG_URL,enabled:false,v2Mode:true,autoReport:'picked',autoReports:['kpis'],lastSuccessAt:null},messages:[],delayed:650};
const mockData={};
const samples={
 kpis:[{date:'2026-10-01',unique_devices:7548,unique_ips:13384,session_ids:10103,ip_ua_sessions:49372,manifest_views:658000,playtime_minutes:732480,bandwidth_bytes:24200000000000}],
 channel:[{date:'2026-10-01',channel_name:'India TV',unique_ips:582761,playtime_minutes:469429}],
 geo:[{date:'2026-10-01',country:'IN',state:'Delhi',city:'NEWDELHI',playtime_minutes:187289.5}],
 devices:[{date:'2026-10-01',platform:'Amazon Fire TV',operating_system:'FireOS',unique_devices:2661,unique_ips:4569}],
 content:[{date:'2026-10-01',content_title:'India TV',manifest_views:112666,unique_ips:3648,unique_devices:2858,session_ids:3676}],
 traffic:[{date:'2026-10-01',hour_ist:'2026-10-01 14:00',unique_ips:1644,session_ids:2292,manifest_views:4000,playtime_minutes:1348,bandwidth_bytes:41000000}]
};
window.chrome={runtime:{lastError:null,getURL:(p)=>'chrome-extension://testextensionid/'+p,sendMessage:(req,cb)=>{
 window.TEST_MOCK.messages.push(req);
 const state=window.TEST_MOCK.state;
 const out=(data)=>cb({ok:true,data});
 if(req.type==='STATE_V2'){
  const summaries=Object.fromEntries(['kpis','channel','geo','devices','content','traffic'].map(id=>{const r=window.TEST_MOCK.rows[id]||[];return [id,{rows:r.length,days:r.length?1:0,from:r.length?'2026-10-01':null,to:r.length?'2026-10-01':null}]}));
  return out({config:{...state},summaries,coverage:{uniqueDays:1},busy:false});
 }
 if(req.type==='SYNC_PICKED'){
   setTimeout(()=>{
    let n=0;for(const id of req.reports){window.TEST_MOCK.rows[id]=samples[id];n+=samples[id].length;}
    state.lastSuccessAt=Date.now();out({rows:n,reports:req.reports.length});
   },window.TEST_MOCK.delayed);return;
 }
 if(req.type==='SAVE_PICKER'){state.dashboardUrl=req.dashboardUrl;return out({config:{...state}});}
 if(req.type==='ENABLE_PICKED'){state.enabled=req.enabled;state.autoReports=req.reports;return out({config:{...state}});}
 if(req.type==='CURRENT_GRAFANA_TAB')return out({url:CONFIG_URL});
 if(req.type==='SCAN_DASHBOARD_PANELS')return out({panels:[{section:'Playtime',title:'Playtime by GEO',mapped:true},{section:'Viewership',title:'Top channel with a very very long descriptive panel name that must wrap rather than overflow the panel browser',mapped:false}]});
 if(req.type==='EXPORT_LOGS')return out({logs:[{at:Date.now(),kind:'test',message:'Synthetic log; no real credentials or production data.'}]});
 if(req.type==='CLEAR_V2'){window.TEST_MOCK.rows={};return out({});}
 return out({config:{...state}});
}},storage:{local:{get:async defaults=>({...defaults,...mockData}),set:async x=>Object.assign(mockData,x)},onChanged:{addListener:()=>{}}},tabs:{create:()=>{}}};
'''

def remove_import(m, imports):
    names,source=m.group(1),m.group(2)
    imports.append(f"const {{{names}}}=__modules[{source!r}];")
    return ''

def bundle():
    pieces=[MOCK,'const __modules={};']
    for name in MODS:
        if name=='report-db.mjs':
            pieces.append("__modules['report-db.mjs']={allReportRows:async()=>({...window.TEST_MOCK.rows})};")
            continue
        s=(ROOT/name).read_text()
        imports=[]
        s=re.sub(r"^import\s+\{(.*?)\}\s+from\s+['\"]\./([^'\"]+)['\"];?\s*$",lambda m:remove_import(m,imports),s,flags=re.M)
        exports=set(re.findall(r'^export\s+(?:(?:async)\s+)?(?:const|function|class)\s+(\w+)',s,flags=re.M))
        for t in re.findall(r'^export\s*\{(.*?)\};?\s*$',s,flags=re.M): exports.update(x.strip() for x in t.split(','))
        s=re.sub(r'^export\s*\{.*?\};?\s*$', '',s,flags=re.M)
        s=re.sub(r'^export\s+(?=(?:async\s+)?(?:const|function|class)\s+)', '',s,flags=re.M)
        if name!='popup.mjs':pieces.append(f"__modules[{name!r}]=(()=>{{\n"+'\n'.join(imports)+'\n'+s+'\nreturn {'+','.join(sorted(exports))+'};\n})();')
        else:pieces.append('(()=>{\n'+'\n'.join(imports)+'\n'+s+'\n})();')
    return '\n'.join(pieces)

async def geom(page):
    return await page.evaluate('''() => {const e=document.querySelector('main'),m=document.querySelector('#metricCatalog'),f=document.querySelector('footer');
      return {root:document.documentElement.scrollWidth,html:document.documentElement.clientWidth,body:document.body.getBoundingClientRect().width,
       mainScroll:e.scrollWidth,mainClient:e.clientWidth,catScroll:m.scrollWidth,catClient:m.clientWidth,
       badButtons:[...document.querySelectorAll('button')].filter(x=>{if(!x.getClientRects().length)return false;const r=x.getBoundingClientRect();return r.right>522||r.left<-1;}).map(x=>x.id||x.textContent.trim().slice(0,20)),
       mainBottom:e.getBoundingClientRect().bottom,footerTop:f.getBoundingClientRect().top}}''')

def check(cond, desc):
    if not cond: raise AssertionError(desc)
    print('PASS',desc)

async def main():
    html=(ROOT/'popup.html').read_text()
    css=(ROOT/'popup.css').read_text()
    logo='data:image/png;base64,'+base64.b64encode((ROOT/'icons/icon48.png').read_bytes()).decode()
    html=html.replace('<link rel="stylesheet" href="popup.css">','<style>'+css+'</style>').replace('<script type="module" src="popup.mjs"></script>','').replace('src="icons/icon48.png"',f'src="{logo}"')
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        context=await browser.new_context(viewport={'width':520,'height':590},device_scale_factor=1,accept_downloads=True)
        page=await context.new_page()
        page.on('dialog',lambda d:asyncio.create_task(d.accept()))
        errors=[]; page.on('pageerror',lambda e:errors.append(str(e)))
        await page.set_content(html,wait_until='domcontentloaded')
        await page.add_script_tag(content=bundle())
        await page.locator('#metricCatalog input').first.wait_for()
        await page.screenshot(path='/mnt/data/Smart-Export-v2.1.1-Popup.png')
        m=await geom(page)
        check(m['root']==520 and m['mainScroll']<=m['mainClient'] and m['catScroll']<=m['catClient'] and not m['badButtons'],'Root width, boxes and buttons have no horizontal overflow')
        check(abs(m['mainBottom']-m['footerTop'])<=1,'Pinned footer never overlaps the scroll container')
        check(await page.locator('#selectedCount').inner_text()=='5 metrics','Five default metrics and search catalog visible')

        # Accordion must retain scroll/focus after toggling a checkbox.
        box=page.locator('.metric-category[data-report="kpis"] input[type=checkbox]').first
        await box.scroll_into_view_if_needed()
        before=await page.locator('#metricCatalog').evaluate('(e)=>e.scrollTop')
        await box.click()
        after=await page.locator('#metricCatalog').evaluate('(e)=>e.scrollTop')
        is_focused=await box.evaluate('(el)=>el===document.activeElement')
        check(abs(before-after)<4 and is_focused,'Checkbox selection keeps accordion position and keyboard focus')
        check(await page.locator('#selectedCount').inner_text()=='4 metrics','Selection count updates immediately')
        # Manual folding and unfolding should not be overridden by rerender.
        summary=page.locator('.metric-category[data-report="kpis"] summary')
        await summary.click()
        await page.wait_for_timeout(80)
        check(not await page.locator('.metric-category[data-report="kpis"]').evaluate('(e)=>e.open'),'Metric accordion closes on click')
        await page.locator('#metricSearch').fill('playtime')
        check(await page.locator('.metric-category').count()>=3,'Search shows only matching categories')
        await page.locator('#clearSearch').click()
        await page.wait_for_timeout(80)
        check(not await page.locator('.metric-category[data-report="kpis"]').evaluate('(e)=>e.open'),'Cleared search restores user-open/closed accordion state')

        await page.locator('button[data-preset="channel"]').click()
        check(await page.locator('#exportFilterBox').is_visible(),'Choosing one channel report reveals optional dimension filter')
        a=await page.evaluate('''() => {let a=document.querySelector('#filterField').getBoundingClientRect(),b=document.querySelector('#exportFilterBox .chevron').getBoundingClientRect();return {center:Math.abs((a.top+a.bottom)/2-(b.top+b.bottom)/2),right:a.right-b.right}}''')
        check(a['center']<5 and 8<a['right']<25,'Filter dropdown arrow horizontally and vertically centered')
        await page.locator('#filterText').fill('News')
        await page.locator('button[data-preset="geo"]').click()
        check(await page.locator('#filterText').input_value()=='','Switching Channel → GEO clears stale dimension filter')

        await page.locator('#automationSettings summary').click()
        viewname='Daily management report with GEO notes'
        await page.locator('#presetName').fill(viewname)
        await page.locator('#savePreset').click()
        check(await page.locator('#savedPresets').input_value()==viewname,'Save view adds a selectable saved preset')
        rect=await page.evaluate('''() => {const ids=['savedPresets','loadPreset','deletePreset'];return Object.fromEntries(ids.map(id=>{const r=document.getElementById(id).getBoundingClientRect();return [id,{x:r.x,y:r.y,w:r.width,h:r.height,right:r.right}]}))}''')
        check(rect['savedPresets']['w']>200 and rect['loadPreset']['y']>rect['savedPresets']['y']+rect['savedPresets']['h'],'Saved-view dropdown has its own full-width row')
        check(rect['loadPreset']['right']+6<=rect['deletePreset']['x'],'Load/Delete action buttons do not collide')
        await page.locator('button[data-preset="channel"]').click()
        await page.locator('#loadPreset').click()
        check(await page.locator('#selectedCount').inner_text()=='1 metric','Load view restores the saved metric configuration')
        await page.locator('#deletePreset').click()
        check(await page.locator('#savedPresets option').count()==1,'Deleting saved view removes the option')

        await page.locator('#advancedSettings summary').click()
        await page.locator('#scanPanels').click()
        check(await page.locator('#panelBrowser .panel-item').count()==2,'Live panel explorer renders mock mapped and unmapped panels')
        g=await geom(page)
        check(g['mainScroll']==g['mainClient'] and not g['badButtons'],'Expanded advanced settings and long panel titles do not bleed')

        # Data fetch: input and metric UI frozen during an in-flight request.
        await page.locator('#syncNow').click()
        await page.wait_for_timeout(55)
        check(await page.locator('#dashboardUrl').is_disabled() and await page.locator('#metricSearch').is_disabled(),'Source and metric selection locked while fetching')
        await page.locator('#downloadXlsx').wait_for(state='visible')
        await page.wait_for_timeout(850)
        check(not await page.locator('#dashboardUrl').is_disabled(),'Controls recover after fetch')
        check(await page.locator('#rowCount').inner_text()=='1','Stored row count updates after successful mocked fetch')
        check(await page.locator('#downloadXlsx').is_enabled(),'Excel action enables after fetched data is ready')
        await page.screenshot(path='/mnt/data/Smart-Export-v2.1.1-Data-Preview.png')
        async with page.expect_download() as download_info:
            await page.locator('#downloadXlsx').click()
        download=await download_info.value
        path='/mnt/data/_smart-export-ui-test.xlsx';await download.save_as(path)
        check(pathlib.Path(path).stat().st_size>2000,'Functional Excel download creates a nonempty XLSX')
        # If dashboard URL has unsaved edits, export must not reuse old dashboard master.
        await page.locator('#dashboardUrl').fill('https://grafana-apj.trafficpeak.live/d/another-id/test?orgId=743')
        check(await page.locator('#downloadXlsx').is_disabled(),'Changing dashboard URL disables stale-data export')
        await page.locator('#dashboardUrl').fill(URL)
        check(await page.locator('#downloadXlsx').is_enabled(),'Restoring dashboard URL safely restores export control')

        # Stress all controls and messages without changing core scripts.
        await page.locator('button[data-preset="all"]').click()
        await page.locator('#dashboardUrl').fill(URL+'Y'*600)
        await page.locator('#feedback').evaluate('(el)=>{el.textContent="ERROR_WITH_VERY_LONG_WORD_"+"X".repeat(850);el.className="feedback error"}')
        await page.locator('#presetName').fill('This is a long human-readable saved view')
        await page.locator('#advancedSettings').scroll_into_view_if_needed()
        await page.screenshot(path='/mnt/data/Smart-Export-v2.1.1-Advanced-Preview.png')
        g=await geom(page)
        check(g['root']==520 and g['mainScroll']==g['mainClient'] and g['catScroll']==g['catClient'] and not g['badButtons'],'Oversized URLs, errors and all metrics cause no horizontal overflow')
        check(await page.locator('#selectedCount').inner_text()=='21 metrics','All 21 supported metrics remain selectable')
        check(not errors,'No JavaScript exceptions in browser interaction suite')
        await context.close();await browser.close()
        print('ALL UI AUDIT CHECKS PASSED')

if __name__=='__main__':asyncio.run(main())

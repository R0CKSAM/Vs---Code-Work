"""Mock Chrome bridge and ES module loader for the v2.2 popup test.
This test fixture deliberately uses synthetic Grafana records only.
"""
import pathlib, re
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


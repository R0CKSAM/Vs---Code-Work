// Isolated browser fixture. All extension APIs use synthetic in-memory records.
const url='https://grafana-apj.trafficpeak.live/d/db7ce6f6-d689-4976-89e5-ddf0b5401f97/sessions-users-monitoring?orgId=743&from=now-7d&to=now&timezone=Asia%2FKolkata&var-filter=';
window.UI_TEST={messages:[],errors:[],downloads:[],confirmations:[],confirm:true,failStorage:false,failSync:false,listeners:[],
 rows:{geo:[{date:'2026-10-20',country:'IN',state:'Delhi',city:'',playtime_minutes:12}]},
 config:{dashboardUrl:url,enabled:true,v2Mode:true,autoReport:'geo',autoReports:[],lastSuccessAt:null,scheduleHourIST:8,autoRefreshDays:3},
 storage:{smartExportSmartPicker_v21:{geo:['playtime_minutes'],kpis:['bandwidth_bytes']},smartExportSavedViews_v21:{}}
};
window.addEventListener('error',e=>UI_TEST.errors.push(e.message));
window.addEventListener('unhandledrejection',e=>UI_TEST.errors.push(String(e.reason)));
window.confirm=message=>{UI_TEST.confirmations.push(message);return UI_TEST.confirm;};
const blobURL=URL.createObjectURL.bind(URL);
URL.createObjectURL=blob=>{UI_TEST.lastBlob=blob;return blobURL(blob);};
HTMLAnchorElement.prototype.click=function(){if(this.download)UI_TEST.downloads.push(this.download);};
window.chrome={runtime:{lastError:null,getManifest:()=>({version:'2.7.2'}),getURL:p=>'/'+p,
 sendMessage(req,reply){UI_TEST.messages.push(req);queueMicrotask(()=>{
  const c=UI_TEST.config,out=data=>reply({ok:true,data});
  if(req.type==='STATE_V2')return out({config:{...c},summaries:Object.fromEntries(Object.entries(UI_TEST.rows).map(([id,rows])=>[id,{rows:rows.length,days:rows.length?1:0,from:rows[0]?.date,to:rows.at(-1)?.date}])),coverage:{}});
  if(req.type==='CURRENT_GRAFANA_TAB')return out({url});
  if(req.type==='SAVE_PICKER'||req.type==='SAVE_SETTINGS'){c.dashboardUrl=req.dashboardUrl;return out({config:{...c}});}
  if(req.type==='ENABLE_PICKED'){Object.assign(c,{enabled:req.enabled,v2Mode:true,autoReport:'picked',autoReports:req.reports});return out({config:{...c}});}
  if(req.type==='ENABLE'){c.enabled=req.enabled;return out({config:{...c}});}
  if(req.type==='SCAN_DASHBOARD_PANELS')return out({panels:[{section:'Playtime',title:'GEO',mapped:true},{section:'Other',title:'Unmapped panel',mapped:false}]});
  if(req.type==='EXPORT_LOGS')return out({logs:[{message:'Synthetic diagnostic record'}]});
  if(req.type==='CLEAR_V2'){UI_TEST.rows={};c.enabled=false;return out({});}
  if(req.type==='SYNC_PICKED'){
   if(UI_TEST.failSync)return reply({ok:false,error:'Synthetic Grafana timeout'});
   for(const id of req.reports)UI_TEST.rows[id]=id==='geo'?[{date:req.from,country:'IN',state:'Delhi',city:'',playtime_minutes:12}]:[];
   c.lastSuccessAt=Date.now();return out({rows:1,reports:req.reports.length});
  }
  reply({ok:false,error:'Unexpected mock request: '+req.type});
 });}},storage:{local:{get:async defaults=>({...defaults,...UI_TEST.storage}),set:async values=>{
  if(UI_TEST.failStorage){UI_TEST.failStorage=false;throw new Error('Synthetic storage failure');}
  Object.assign(UI_TEST.storage,values);
 }},onChanged:{addListener(fn){UI_TEST.listeners.push(fn);}}},tabs:{create:async details=>{UI_TEST.opened=details;}}};

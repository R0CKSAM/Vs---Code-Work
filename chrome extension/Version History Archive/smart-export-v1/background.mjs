import { DEFAULT_CONFIG, FALLBACK_DATASOURCE_UID, PANEL_NAME, parseDashboardUrl, assertDateRange, buildGeoSql, parseGrafanaFrames, summarize, istToday, istHour, addDays, datesForLastCompleteDays } from './core.mjs';
import { replaceRange, readDataset, clearDataset } from './database.mjs';
const CONFIG_KEY='smartExportConfig', LOG_KEY='smartExportLogs', ACTIVITY_KEY='smartExportActivity';
const ALARM='smartExportDailyCheck';
let busy=false;
const cleanError=e=>String(e?.message||e||'Unknown error').slice(0,700);
async function log(level,message){
  const old=(await chrome.storage.local.get({[LOG_KEY]:[]}))[LOG_KEY];
  const lines=[{at:new Date().toISOString(),level,message:cleanError(message)},...old].slice(0,70);
  await chrome.storage.local.set({[LOG_KEY]:lines});
}
async function config(){const r=await chrome.storage.local.get({[CONFIG_KEY]:DEFAULT_CONFIG});return {...DEFAULT_CONFIG,...r[CONFIG_KEY]};}
async function patchConfig(p){const c={...await config(),...p};await chrome.storage.local.set({[CONFIG_KEY]:c});return c;}
async function activity(message,kind='info'){
  await chrome.storage.local.set({[ACTIVITY_KEY]:{message:String(message).slice(0,550),kind,time:Date.now()}});
}
function findMatchingURL(url, uid){try{return new URL(url).pathname.split('/')[2]===uid;}catch{return false;}}
async function findDashboardTab(spec){
  const tabs=await chrome.tabs.query({url:`${spec.origin}/*`});
  const matches=tabs.filter(t=>t.id && t.url && findMatchingURL(t.url,spec.uid));
  if(!matches.length)throw new Error('Open your saved Grafana dashboard in Chrome and sign in. Keep that tab open for daily exports.');
  // Prefer the last active Grafana dashboard, otherwise keep the existing background tab.
  return matches.find(t=>t.active&&!t.discarded)||matches.find(t=>!t.discarded)||matches[0];
}

async function fetchDailyViaGrafana(tabId, spec, sql, fromMs, toMs){
  // Runs INSIDE the logged-in Grafana origin. No cookie, password, token or data is sent elsewhere.
  const injected=await chrome.scripting.executeScript({
    target:{tabId},world:'MAIN',args:[{uid:spec.uid,orgId:spec.orgId,sql,fromMs,toMs,
      fallbackDatasourceUid:FALLBACK_DATASOURCE_UID,panelName:PANEL_NAME}],
    func:async params=>{
      try{
        if(location.origin!=='https://grafana-apj.trafficpeak.live')throw new Error('Incorrect Grafana origin.');
        if(!location.pathname.startsWith(`/d/${params.uid}/`))throw new Error('Grafana tab is not on the saved dashboard.');
        const dashResp=await fetch(`/api/dashboards/uid/${encodeURIComponent(params.uid)}`,{credentials:'same-origin',cache:'no-store'});
        if(!dashResp.ok)throw new Error(`Dashboard inspection failed (HTTP ${dashResp.status}); check Grafana login and permissions.`);
        const doc=await dashResp.json();
        const dashboard=doc.dashboard||{};
        const panels=[];
        for(const p of dashboard.panels||[]){panels.push(p,...(p.panels||[]));}
        const panel=panels.find(p=>p.title===params.panelName);
        if(!panel)throw new Error(`Dashboard has no '${params.panelName}' panel. Export stopped to avoid wrong data.`);
        const raw=panel.targets?.[0]?.rawSql||'';
        if(!raw.includes('count() * 6 / 60.0')||!raw.includes("reqPath LIKE '%.ts'")){
          throw new Error('The source panel SQL has changed. Verify the calculation before exporting.');
        }
        let ds=panel.targets?.[0]?.datasource?.uid;
        if(!ds||ds.includes('${')){
          ds=(dashboard.templating?.list||[]).find(v=>v.type==='adhoc' && v.datasource?.uid)?.datasource.uid;
        }
        if(!ds||ds.includes('${'))ds=params.fallbackDatasourceUid;
        if(!ds)throw new Error('Could not resolve Hydrolix data source ID.');
        const headers={'Content-Type':'application/json','Accept':'application/json','X-Grafana-Org-Id':String(params.orgId)};
        const body={queries:[{datasource:{type:'hydrolix-hydrolix-datasource',uid:ds},refId:'A',format:1,
          rawSql:params.sql,intervalMs:60000,maxDataPoints:100000}],from:String(params.fromMs),to:String(params.toMs)};
        const response=await fetch('/api/ds/query',{method:'POST',headers,credentials:'same-origin',body:JSON.stringify(body)});
        const reply=await response.text();
        let data;try{data=JSON.parse(reply);}catch{throw new Error('Grafana query did not return JSON. Your session may have expired.');}
        if(!response.ok)throw new Error(`Grafana query failed HTTP ${response.status}: ${data?.message||data?.error||'access/query denied'}`);
        // Return data frame only, never session details, personal data, headers or tokens.
        return {ok:true,data,ds,sourcePanelId:panel.id};
      }catch(e){return {ok:false,error:String(e?.message||e).slice(0,700)};}
    }
  });
  const result=injected?.[0]?.result;
  if(!result)throw new Error('Grafana script returned no data; check Chrome permissions or reload the tab.');
  if(!result.ok)throw new Error(result.error);
  return result;
}
async function doSync(from,to,{automatic=false}={}){
  if(busy)throw new Error('Another export is already running.');
  busy=true;
  await activity(automatic?'Updating the latest completed dates…':`Fetching ${from} to ${to}…`);
  try{
    const c=await config();
    const spec=parseDashboardUrl(c.dashboardUrl);
    const days=assertDateRange(from,to);
    const tab=await findDashboardTab(spec);
    if(tab.discarded)throw new Error('Grafana tab is discarded. Open the dashboard once, then retry.');
    // Even if the saved URL had no filter, an employee may have applied one in the live tab.
    // Reject it rather than silently exporting unfiltered data.
    const live=parseDashboardUrl(tab.url);
    if(live.datasetKey!==spec.datasetKey)throw new Error('The live Grafana tab has different organization/filter settings. Re-select or refresh the saved dashboard.');
    const sql=buildGeoSql(from,to);
    const fromMs=Date.parse(`${from}T00:00:00Z`)-19800000;
    const toMs=Date.parse(`${addDays(to,1)}T00:00:00Z`)-19800000;
    const {data,sourcePanelId}=await fetchDailyViaGrafana(tab.id,spec,sql,fromMs,toMs);
    const rows=parseGrafanaFrames(data,from,to);
    if(!rows.length) {
      await log('warning',`No GEO rows returned for ${from} to ${to} (Panel ${sourcePanelId}). Existing data was preserved.`);
      await activity('No data returned. Nothing was changed; check Grafana query and selected dates.','warning');
      return {rows:0,days,empty:true};
    }
    if(rows.length>100000)throw new Error('More than 100,000 GEO rows returned; sync a shorter date range.');
    await replaceRange(spec.datasetKey,from,to,rows);
    const updates={lastSuccessAt:new Date().toISOString(),lastDateFrom:from,lastDateTo:to};
    if(automatic) updates.lastAutoDate=to;
    await patchConfig(updates);
    await activity(`${rows.length.toLocaleString()} GEO groups updated across ${days} days.`, 'success');
    await log('success', `${automatic?'Automatic':'Manual'} sync: ${from}…${to}, ${rows.length} rows`);
    await chrome.action.setBadgeText({text:''});
    return {rows:rows.length,days};
  }catch(e){
    const reason=cleanError(e);
    await log('error',reason);
    await activity(reason,'error');
    await chrome.action.setBadgeText({text:'!'});
    await chrome.action.setBadgeBackgroundColor({color:'#C84655'});
    throw e;
  }finally{busy=false;}
}
async function getState(){
  const c=await config();
  let rows=[];
  try{rows=await readDataset(parseDashboardUrl(c.dashboardUrl).datasetKey);}catch{}
  const details=summarize(rows);
  const other=await chrome.storage.local.get({[ACTIVITY_KEY]:null,[LOG_KEY]:[]});
  return {config:c,summary:details,activity:other[ACTIVITY_KEY],logs:other[LOG_KEY].slice(0,12),busy};
}
async function saveSettings(request){
  const old=await config();
  const url=String(request.dashboardUrl||'').trim();
  const spec=parseDashboardUrl(url);
  if(request.enabled && !spec)throw new Error('Select your Grafana dashboard.');
  // If source changes, suspend scheduling until owner explicitly re-enables it.
  const oldKey=parseDashboardUrl(old.dashboardUrl).datasetKey;
  const change=spec.datasetKey!==oldKey;
  const enabled=change?false:!!request.enabled;
  return patchConfig({dashboardUrl:url,orgId:spec.orgId,enabled});
}
async function automaticCheck(){
  const c=await config();
  if(!c.enabled || istHour()<c.scheduleHourIST || busy)return;
  const yesterday=addDays(istToday(),-1);
  if(c.lastAutoDate===yesterday)return;
  // Reconcile 3 days by default to correct late logs. After a long browser outage,
  // automatic sync is deliberately limited; manual backfill can fill missed periods.
  const from=addDays(yesterday,1-c.autoRefreshDays);
  try{await doSync(from,yesterday,{automatic:true});}
  catch(e){/* doSync already logged. The next hourly alarm will retry. */}
}
chrome.runtime.onMessage.addListener((msg,_sender,reply)=>{
  (async()=>{
    switch(msg?.type){
      case 'STATE':return await getState();
      case 'SAVE_SETTINGS':return {config:await saveSettings(msg)};
      case 'SYNC':return await doSync(msg.from,msg.to);
      case 'ENABLE':{
        const c=await config();parseDashboardUrl(c.dashboardUrl);
        return {config:await patchConfig({enabled:!!msg.enabled})};
      }
      case 'CLEAR_DATA':{
        if(busy)throw new Error('Cannot erase the master while a sync is running.');
        const spec=parseDashboardUrl((await config()).dashboardUrl);
        await clearDataset(spec.datasetKey);await patchConfig({lastSuccessAt:null,lastAutoDate:null});
        await log('info','Master GEO data manually cleared.');return {ok:true};
      }
      case 'EXPORT_LOGS':return {logs:(await chrome.storage.local.get({[LOG_KEY]:[]}))[LOG_KEY]};
      case 'CURRENT_GRAFANA_TAB':{
        const t=await chrome.tabs.query({active:true,currentWindow:true});
        const u=t[0]?.url||'';parseDashboardUrl(u);return {url:u};
      }
      default: throw new Error('Unknown Smart Export command.');
    }
  })().then(data=>reply({ok:true,data})).catch(e=>reply({ok:false,error:cleanError(e)}));
  return true;
});
chrome.alarms.onAlarm.addListener(a=>{if(a.name===ALARM)automaticCheck();});
async function ensureAlarm(){await chrome.alarms.create(ALARM,{delayInMinutes:1,periodInMinutes:60});}
chrome.runtime.onInstalled.addListener(()=>{ensureAlarm().catch(console.error);});
chrome.runtime.onStartup.addListener(()=>{ensureAlarm().then(automaticCheck).catch(console.error);});
// If Chrome cleared the alarm unexpectedly, recreate it when worker starts.
chrome.alarms.get(ALARM).then(a=>{if(!a)ensureAlarm();}).catch(()=>{});

import { DEFAULT_CONFIG, FALLBACK_DATASOURCE_UID, PANEL_NAME, parseDashboardUrl, assertDateRange, buildGeoSql, parseGrafanaFrames, summarize, istToday, istHour, addDays, datesForLastCompleteDays } from './core.mjs';
import { replaceRange, readDataset, clearDataset } from './database.mjs';
import {REPORT_ORDER,ALL_REPORT_ORDER,REPORTS,datasetsFor,sqlForReport,parseReportFrames,assertSourcePanels} from './reports.mjs';
import {putReportsAtomically,allReportRows,clearReportRows} from './report-db.mjs';
import {validateReports} from './metric-catalog.mjs';
const CONFIG_KEY='smartExportConfig', LOG_KEY='smartExportLogs', ACTIVITY_KEY='smartExportActivity';
const ALARM='smartExportDailyCheck';
let busy=false;
let configQueue=Promise.resolve();
const V2_DEFAULT={selectedReport:'executive',v2Mode:false,autoReport:'geo',autoReports:[],v2LastAutoDates:{}};
const cleanError=e=>String(e?.message||e||'Unknown error').slice(0,700);
async function log(level,message){
  const stored=(await chrome.storage.local.get({[LOG_KEY]:[]}))[LOG_KEY],old=Array.isArray(stored)?stored:[];
  const lines=[{at:new Date().toISOString(),level,message:cleanError(message)},...old].slice(0,70);
  await chrome.storage.local.set({[LOG_KEY]:lines});
}
async function config(){const r=await chrome.storage.local.get({[CONFIG_KEY]:DEFAULT_CONFIG});return {...DEFAULT_CONFIG,...r[CONFIG_KEY]};}
async function patchConfig(p){const task=configQueue.catch(()=>{}).then(async()=>{if(busy&&('dashboardUrl' in p||p.enabled===true))throw new Error('Wait for the current fetch before changing its source or enabling daily updates.');const c={...await config(),...p};await chrome.storage.local.set({[CONFIG_KEY]:c});return c;});configQueue=task;return task;}
async function bestEffort(task){try{await task();}catch(e){console.warn('Smart Export status update failed:',cleanError(e));}}
async function activity(message,kind='info'){
  await chrome.storage.local.set({[ACTIVITY_KEY]:{message:String(message).slice(0,550),kind,time:Date.now()}});
}
function findMatchingURL(url, uid){try{return new URL(url).pathname.split('/')[2]===uid;}catch{return false;}}
async function findDashboardTab(spec){
  const tabs=await chrome.tabs.query({url:`${spec.origin}/*`});
  const matches=tabs.filter(t=>{try{return t.id&&parseDashboardUrl(t.url).datasetKey===spec.datasetKey;}catch{return false;}});
  if(!matches.length)throw new Error('Open your saved Grafana dashboard with the same organization and filters. If you changed filters, choose Connect Grafana or Get data to select the current dashboard.');
  // Prefer the last active Grafana dashboard, otherwise keep the existing background tab.
  return matches.find(t=>t.active&&!t.discarded)||matches.find(t=>!t.discarded)||matches[0];
}

async function fetchDailyViaGrafana(tabId, spec, sql, fromMs, toMs){
  // Runs INSIDE the logged-in Grafana origin. No cookie, password, token or data is sent elsewhere.
  const injected=await chrome.scripting.executeScript({
    target:{tabId},world:'MAIN',args:[{uid:spec.uid,orgId:spec.orgId,sql,fromMs,toMs,
      fallbackDatasourceUid:FALLBACK_DATASOURCE_UID,panelName:PANEL_NAME,filters:spec.filters,filterParams:spec.filterParams}],
    func:async params=>{
      try{
        if(location.origin!=='https://grafana-apj.trafficpeak.live')throw new Error('Incorrect Grafana origin.');
        if(!location.pathname.startsWith(`/d/${params.uid}/`))throw new Error('Grafana tab is not on the saved dashboard.');
        const checkSource=()=>{
          const live=new URL(location.href||location.origin+location.pathname);
          const filters=[...new Set(live.searchParams.getAll('var-filter').filter(v=>v.trim()))].sort();
          if((live.searchParams.get('orgId')||'743')!==params.orgId||JSON.stringify(filters)!==JSON.stringify(params.filterParams||[])||[...live.searchParams].some(([k,v])=>k.startsWith('var-')&&!['var-filter','var-hdx_query_errors'].includes(k)&&v.trim()))throw new Error('Grafana filters changed while fetching. Click Get data again to use the current selection.');
        };checkSource();
        const dashResp=await fetch(`/api/dashboards/uid/${encodeURIComponent(params.uid)}`,{credentials:'same-origin',cache:'no-store',headers:{'X-Grafana-Org-Id':String(params.orgId)},signal:AbortSignal.timeout(15000)});
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
          rawSql:params.sql,filters:params.filters||[],intervalMs:60000,maxDataPoints:100000}],from:String(params.fromMs),to:String(params.toMs)};
        checkSource();
        const response=await fetch('/api/ds/query',{method:'POST',headers,credentials:'same-origin',body:JSON.stringify(body),signal:AbortSignal.timeout(90000)});
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

/* V2 query: validates the live dashboard's panel definitions before issuing each
   fixed SQL template. Queries run using the signed-in Grafana session only. */
async function fetchV2ViaGrafana(tabId,spec,report,sql,fromMs,toMs){
  const r=await chrome.scripting.executeScript({target:{tabId},world:'MAIN',args:[{
    uid:spec.uid,orgId:spec.orgId,sql,fromMs,toMs,report,
    sourceIds:REPORTS[report].sourceIds,fallbackDatasourceUid:FALLBACK_DATASOURCE_UID
  }],func:async p=>{
    try{
      if(location.origin!=='https://grafana-apj.trafficpeak.live'||!location.pathname.startsWith(`/d/${p.uid}/`))throw new Error('Wrong Grafana tab.');
      const d=await fetch(`/api/dashboards/uid/${encodeURIComponent(p.uid)}`,{credentials:'same-origin',cache:'no-store',headers:{'X-Grafana-Org-Id':String(p.orgId)},signal:AbortSignal.timeout(15000)});
      if(!d.ok)throw new Error(`Grafana dashboard access failed: HTTP ${d.status}`);
      const j=await d.json(),dash=j.dashboard||{},panels=[];
      for(const x of dash.panels||[])panels.push(x,...(x.panels||[]));
      const selected=panels.filter(x=>p.sourceIds.includes(x.id)).map(x=>({id:x.id,title:x.title,targets:x.targets}));
      for(const id of p.sourceIds)if(!selected.some(x=>x.id===id))throw new Error(`Missing Grafana source panel ${id}.`);
      let ds=selected.flatMap(x=>x.targets||[]).map(x=>x.datasource?.uid).find(uid=>uid&&!uid.includes('${'));
      if(!ds||ds.includes('${'))ds=(dash.templating?.list||[]).find(x=>x.type==='adhoc'&&x.datasource?.uid)?.datasource?.uid;
      if(!ds||ds.includes('${'))ds=p.fallbackDatasourceUid;
      if(!ds)throw new Error('No Hydrolix datasource UID.');
      return {ok:true,ds,panels:selected};
    }catch(e){return {ok:false,error:String(e?.message||e).slice(0,550)};}
  }});
  const result=r?.[0]?.result;
  if(!result)throw new Error('Grafana returned no query response to the extension.');
  if(!result.ok)throw new Error(result.error);
  assertSourcePanels(report,result.panels);
  // Validate source SQL before issuing a query, not after consuming its response.
  const query=await chrome.scripting.executeScript({target:{tabId},world:'MAIN',args:[{
    uid:spec.uid,orgId:spec.orgId,ds:result.ds,sql,fromMs,toMs,filters:spec.filters,filterParams:spec.filterParams
  }],func:async p=>{
    try{
      if(location.origin!=='https://grafana-apj.trafficpeak.live'||!location.pathname.startsWith(`/d/${p.uid}/`))throw new Error('Grafana navigated away from the selected dashboard.');
      const live=new URL(location.href||location.origin+location.pathname);
      const filters=[...new Set(live.searchParams.getAll('var-filter').filter(v=>v.trim()))].sort();
      if((live.searchParams.get('orgId')||'743')!==p.orgId||JSON.stringify(filters)!==JSON.stringify(p.filterParams||[])||[...live.searchParams].some(([k,v])=>k.startsWith('var-')&&!['var-filter','var-hdx_query_errors'].includes(k)&&v.trim()))throw new Error('Grafana filters changed while fetching. Click Get data again to use the current selection.');
      const body={queries:[{datasource:{type:'hydrolix-hydrolix-datasource',uid:p.ds},refId:'A',format:1,rawSql:p.sql,filters:p.filters||[],intervalMs:60000,maxDataPoints:100000}],from:String(p.fromMs),to:String(p.toMs)};
      const response=await fetch('/api/ds/query',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','Accept':'application/json','X-Grafana-Org-Id':String(p.orgId)},body:JSON.stringify(body),signal:AbortSignal.timeout(90000)});
      let data;try{data=await response.json();}catch{throw new Error('Grafana returned non-JSON data. Check sign-in and try a smaller date range.');}
      if(!response.ok)throw new Error(`Grafana query HTTP ${response.status}: ${data?.message||data?.error||'request failed'}`);
      return {ok:true,data};
    }catch(e){return {ok:false,error:e?.name==='TimeoutError'?'Grafana query timed out after 90 seconds. Choose fewer panels or a shorter date range.':String(e?.message||e).slice(0,550)};}
  }});
  const response=query?.[0]?.result;
  if(!response?.ok)throw new Error(response?.error||'Grafana tab closed or returned no query response.');
  return response.data;
}

async function migrateLegacyGeo(spec){
  const key='smartExportV2Migrated_'+spec.datasetKey;
  const seen=await chrome.storage.local.get({[key]:false});
  if(seen[key])return;
  const old=await readDataset(spec.datasetKey);
  const data=await allReportRows(spec.datasetKey);
  if(old.length && !data.geo.length){
    const sorted=[...old].sort((a,b)=>a.date.localeCompare(b.date));
    await putReportsAtomically(spec.datasetKey,sorted[0].date,sorted.at(-1).date,{geo:old.map(x=>({date:x.date,country:x.country,state:x.state,city:x.city,playtime_minutes:x.playtime_minutes}))});
    await bestEffort(()=>log('info',`Migrated ${old.length} GEO rows from v1 master without deleting v1 data.`));
  }
  await chrome.storage.local.set({[key]:true});
}

async function syncV2(from,to,report,{automatic=false,typesOverride=null}={}){
  if(busy)throw new Error('An export is already running.');
  const types=typesOverride?validateReports(typesOverride):datasetsFor(report);
  const label=report==='picked'?`${types.length} selected categories`:report==='executive'?'all six reports':REPORTS[report]?.title;
  const marker=report==='picked'?`picked:${types.join(',')}`:report;
  if(!types.length||types.some(x=>!ALL_REPORT_ORDER.includes(x)))throw new Error('Unknown export variant.');
  busy=true;
  try{
    await activity(`Reading ${label} for ${from} – ${to}…`);
    const started=Date.now();
    const days=assertDateRange(from,to);
    if(types.length>1&&days>31)throw new Error('Multiple categories are limited to 31 days per fetch. Select a smaller range or export one category.');
    const minuteCount=types.filter(id=>id.endsWith('_1m')||id==='viewership_minute').length;
    const fiveCount=types.filter(id=>id.endsWith('_5m')).length;
    if(days*(minuteCount*1440+fiveCount*288)>115000)
      throw new Error('Minute-level query would exceed the safe data limit. Choose fewer Time Series panels or a shorter date range. No saved data changed.');
    const conf=await config(),spec=parseDashboardUrl(conf.dashboardUrl);
    const tab=await findDashboardTab(spec);
    if(tab.discarded)throw new Error('Grafana tab is sleeping. Open it once and retry.');
    const activeSpec=parseDashboardUrl(tab.url);
    if(activeSpec.datasetKey!==spec.datasetKey)throw new Error('The open dashboard has a different org/filter than the saved one.');
    const fromMs=Date.parse(`${from}T00:00:00Z`)-19800000;
    const toMs=Date.parse(`${addDays(to,1)}T00:00:00Z`)-19800000;
    const all={};
    for(let i=0;i<types.length;i++){
      if(Date.now()-started>180000)throw new Error('Request is taking too long. Choose fewer panels or a shorter date range. No saved data changed.');
      const id=types[i];
      await activity(`Reading ${i+1}/${types.length}: ${REPORTS[id].title}…`);
      const sql=sqlForReport(id,from,to,spec.filters);
      const payload=await fetchV2ViaGrafana(tab.id,spec,id,sql,fromMs,toMs);
      const diagnostics={};
      const rows=parseReportFrames(payload,id,from,to,diagnostics);
      if(diagnostics.duplicatesSkipped)await bestEffort(()=>log('warning',`${REPORTS[id].title}: ignored ${diagnostics.duplicatesSkipped} repeated identical group(s) from ${diagnostics.frameCount} Grafana frames.`));
      if(diagnostics.missingValues)await bestEffort(()=>log('warning',`${REPORTS[id].title}: ${diagnostics.missingValues} missing measurement(s) retained as blank values.`));
      if(!rows.length)throw new Error(`${REPORTS[id].title} returned no rows. Nothing was merged; try a different date range or a single report.`);
      all[id]=rows;
    }
    // Only update local master when every requested report succeeded.
    const recordCount=await putReportsAtomically(spec.datasetKey,from,to,all);
    if(all.geo){
      // Preserve compatibility with the existing GEO v1 master. The new v2 master is authoritative.
      try{await replaceRange(spec.datasetKey,from,to,all.geo);}
      catch(e){await bestEffort(()=>log('warning',`V2 GEO saved; legacy v1 GEO mirror failed: ${cleanError(e)}`));}
    }
    const updates={lastSuccessAt:new Date().toISOString(),lastDateFrom:from,lastDateTo:to,selectedReport:report==='picked'?(types.length===1?types[0]:'executive'):report};
    if(automatic){const byDate={...(conf.v2LastAutoDates||{})};byDate[marker]=to;updates.v2LastAutoDates=byDate;}
    let metadataWarning='';
    try{await patchConfig(updates);}catch{metadataWarning='Reports were saved, but the last-update status could not be stored.';}
    await bestEffort(()=>activity(metadataWarning||`${recordCount.toLocaleString('en-IN')} records merged for ${label} (${days} days).`,metadataWarning?'warning':'success'));
    await bestEffort(()=>log('success',`${automatic?'Daily':'Manual'} v2 ${report}: ${from}..${to}, ${recordCount} rows.`));
    await bestEffort(()=>chrome.action.setBadgeText({text:''}));
    return {rows:recordCount,days,reports:types.length,warning:metadataWarning};
  }catch(e){
    await bestEffort(()=>log('error',`${report} export: ${cleanError(e)}`));
    await bestEffort(()=>activity(cleanError(e),'error'));
    await bestEffort(()=>chrome.action.setBadgeText({text:'!'}));
    await bestEffort(()=>chrome.action.setBadgeBackgroundColor({color:'#C84655'}));
    throw e;
  }finally{busy=false;}
}
async function getV2State(){
  const conf={...V2_DEFAULT,...await config()},spec=parseDashboardUrl(conf.dashboardUrl);
  await migrateLegacyGeo(spec);
  const datasets=await allReportRows(spec.datasetKey);
  const summaries={};
  for(const id of ALL_REPORT_ORDER)summaries[id]=summarize(datasets[id]);
  const logdata=await chrome.storage.local.get({[ACTIVITY_KEY]:null,[LOG_KEY]:[]});
  const dates=new Set();for(const rows of Object.values(datasets))for(const row of rows)dates.add(row.date);
  return {config:conf,summaries,coverage:{uniqueDays:dates.size},busy,activity:logdata[ACTIVITY_KEY],logs:(Array.isArray(logdata[LOG_KEY])?logdata[LOG_KEY]:[]).slice(0,12)};
}
async function saveV2Settings(payload){
  if(busy)throw new Error('Wait for the current fetch before changing the data source.');
  const conf=await config(),url=String(payload.dashboardUrl||'').trim(),spec=parseDashboardUrl(url);
  const report=String(payload.report||'');if(!REPORTS[report])throw new Error('Invalid report choice.');
  const before=parseDashboardUrl(conf.dashboardUrl);
  const changed=spec.datasetKey!==before.datasetKey;
  const scheduleChanged=!!conf.enabled && !!conf.v2Mode && report!==(conf.autoReport||'geo');
  const changes={dashboardUrl:spec.url,orgId:spec.orgId,selectedReport:report};
  if(changed||scheduleChanged)changes.enabled=false;
  if(changed)changes.v2LastAutoDates={};
  return await patchConfig(changes);
}

async function savePickerSettings(payload){
  if(busy)throw new Error('Wait for the current fetch before changing the data source or report selection.');
  const conf=await config(),spec=parseDashboardUrl(String(payload.dashboardUrl||'').trim());
  const ids=validateReports(payload.reports);
  const before=parseDashboardUrl(conf.dashboardUrl);
  const sourceChanged=spec.datasetKey!==before.datasetKey;
  const scheduled=(conf.autoReport==='picked' ? (conf.autoReports||[]) : (conf.autoReport==='executive'?REPORT_ORDER:[conf.autoReport||'geo']));
  const pickChanged=JSON.stringify(validateReports(ids))!==JSON.stringify(scheduled);
  const updates={dashboardUrl:spec.url,orgId:spec.orgId,selectedReport:ids.length===1?ids[0]:'executive'};
  if(sourceChanged||(conf.enabled&&pickChanged))updates.enabled=false;
  if(sourceChanged)updates.v2LastAutoDates={};
  return await patchConfig(updates);
}

async function doSync(from,to,{automatic=false}={}){
  if(busy)throw new Error('Another export is already running.');
  busy=true;
  try{
    await activity(automatic?'Updating the latest completed dates…':`Fetching ${from} to ${to}…`);
    const c=await config();
    const spec=parseDashboardUrl(c.dashboardUrl);
    const days=assertDateRange(from,to);
    const tab=await findDashboardTab(spec);
    if(tab.discarded)throw new Error('Grafana tab is discarded. Open the dashboard once, then retry.');
    // Even if the saved URL had no filter, an employee may have applied one in the live tab.
    // Reject it rather than silently exporting unfiltered data.
    const live=parseDashboardUrl(tab.url);
    if(live.datasetKey!==spec.datasetKey)throw new Error('The live Grafana tab has different organization/filter settings. Re-select or refresh the saved dashboard.');
    const sql=buildGeoSql(from,to,spec.filters);
    const fromMs=Date.parse(`${from}T00:00:00Z`)-19800000;
    const toMs=Date.parse(`${addDays(to,1)}T00:00:00Z`)-19800000;
    const {data,sourcePanelId}=await fetchDailyViaGrafana(tab.id,spec,sql,fromMs,toMs);
    const diagnostics={};
    const rows=parseGrafanaFrames(data,from,to,diagnostics);
    if(diagnostics.duplicatesSkipped)await log('warning',`GEO: ignored ${diagnostics.duplicatesSkipped} identical duplicate group(s) from ${diagnostics.frameCount} Grafana frames.`);
    if(!rows.length) {
      await log('warning',`No GEO rows returned for ${from} to ${to} (Panel ${sourcePanelId}). Existing data was preserved.`);
      await activity('No data returned. Nothing was changed; check Grafana query and selected dates.','warning');
      return {rows:0,days,empty:true};
    }
    if(rows.length>100000)throw new Error('More than 100,000 GEO rows returned; sync a shorter date range.');
    await replaceRange(spec.datasetKey,from,to,rows);
    const updates={lastSuccessAt:new Date().toISOString(),lastDateFrom:from,lastDateTo:to};
    if(automatic) updates.lastAutoDate=to;
    await bestEffort(()=>patchConfig(updates));
    await bestEffort(()=>activity(`${rows.length.toLocaleString()} GEO groups updated across ${days} days.`, 'success'));
    await bestEffort(()=>log('success', `${automatic?'Automatic':'Manual'} sync: ${from}…${to}, ${rows.length} rows`));
    await bestEffort(()=>chrome.action.setBadgeText({text:''}));
    return {rows:rows.length,days};
  }catch(e){
    const reason=cleanError(e);
    await bestEffort(()=>log('error',reason));
    await bestEffort(()=>activity(reason,'error'));
    await bestEffort(()=>chrome.action.setBadgeText({text:'!'}));
    await bestEffort(()=>chrome.action.setBadgeBackgroundColor({color:'#C84655'}));
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
  if(busy)throw new Error('Wait for the current fetch before changing settings.');
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
  const picked=c.v2Mode&&c.autoReport==='picked'?validateReports(c.autoReports||[]):null;
  const marker=picked?`picked:${picked.join(',')}`:(c.autoReport||'geo');
  if(c.v2Mode ? (c.v2LastAutoDates||{})[marker]===yesterday : c.lastAutoDate===yesterday)return;
  // Reconcile 3 days by default to correct late logs. After a long browser outage,
  // automatic sync is deliberately limited; manual backfill can fill missed periods.
  const from=addDays(yesterday,1-c.autoRefreshDays);
  try{
    if(c.v2Mode)await syncV2(from,yesterday,picked?'picked':(c.autoReport||'geo'),{automatic:true,typesOverride:picked});
    else await doSync(from,yesterday,{automatic:true});
  }
  catch(e){/* doSync already logged. The next hourly alarm will retry. */}
}
chrome.runtime.onMessage.addListener((msg,_sender,reply)=>{
  (async()=>{
    switch(msg?.type){
      case 'STATE_V2':return await getV2State();
      case 'SAVE_PICKER':return {config:await savePickerSettings(msg)};
      case 'SYNC_PICKED':return await syncV2(msg.from,msg.to,'picked',{typesOverride:validateReports(msg.reports)});
      case 'ENABLE_PICKED':{
        if(busy&&msg.enabled)throw new Error('Wait for the current fetch before enabling daily updates.');
        const c=await config(),reports=validateReports(msg.reports);
        parseDashboardUrl(c.dashboardUrl);
        return {config:await patchConfig({enabled:!!msg.enabled,v2Mode:true,autoReport:'picked',autoReports:reports,selectedReport:reports.length===1?reports[0]:'executive'})};
      }
      case 'SAVE_V2':return {config:await saveV2Settings(msg)};
      case 'SYNC_V2':return await syncV2(msg.from,msg.to,msg.report);
      case 'ENABLE_V2':{
        if(busy&&msg.enabled)throw new Error('Wait for the current fetch before enabling daily updates.');
        const c=await config();const report=msg.report;
        if(!REPORTS[report])throw new Error('Invalid automated report type.');
        parseDashboardUrl(c.dashboardUrl);
        return {config:await patchConfig({enabled:!!msg.enabled,v2Mode:true,autoReport:report,selectedReport:report})};
      }
      case 'CLEAR_V2':{
        if(busy)throw new Error('Cannot clear data while running a query.');
        busy=true;try{
        const c=await config(),spec=parseDashboardUrl(c.dashboardUrl);
        await clearReportRows(spec.datasetKey);
        await patchConfig({enabled:false,lastSuccessAt:null,v2LastAutoDates:{}});
        await bestEffort(()=>log('warning','Local v2 report master cleared by user; original v1 GEO store retained.'));
        return {ok:true};
        }finally{busy=false;}
      }
      case 'STATE':return await getState();
      case 'SAVE_SETTINGS':return {config:await saveSettings(msg)};
      case 'SYNC':return await doSync(msg.from,msg.to);
      case 'ENABLE':{
        const c=await config();parseDashboardUrl(c.dashboardUrl);
        return {config:await patchConfig({enabled:!!msg.enabled})};
      }
      case 'CLEAR_DATA':{
        if(busy)throw new Error('Cannot erase the master while a sync is running.');
        busy=true;try{
        const spec=parseDashboardUrl((await config()).dashboardUrl);
        await clearDataset(spec.datasetKey);await patchConfig({lastSuccessAt:null,lastAutoDate:null});
        await log('info','Master GEO data manually cleared.');return {ok:true};
        }finally{busy=false;}
      }
      case 'EXPORT_LOGS':return {logs:(await chrome.storage.local.get({[LOG_KEY]:[]}))[LOG_KEY]};
      case 'SCAN_DASHBOARD_PANELS':{
        const c=await config(),spec=parseDashboardUrl(c.dashboardUrl),tab=await findDashboardTab(spec);
        if(tab.discarded)throw new Error('Open your Grafana dashboard tab before scanning panels.');
        const out=await chrome.scripting.executeScript({target:{tabId:tab.id},world:'MAIN',args:[spec.uid,spec.orgId],func:async (uid,orgId)=>{
          try{
            if(location.origin!=='https://grafana-apj.trafficpeak.live'||!location.pathname.startsWith(`/d/${uid}/`))throw new Error('Wrong Grafana dashboard tab.');
            const r=await fetch(`/api/dashboards/uid/${encodeURIComponent(uid)}`,{credentials:'same-origin',cache:'no-store',headers:{'X-Grafana-Org-Id':String(orgId)},signal:AbortSignal.timeout(15000)});
            if(!r.ok)throw new Error(`Dashboard access failed (HTTP ${r.status}).`);
            const j=await r.json(),list=[];let section='Other panels';
            for(const panel of j.dashboard?.panels||[]){
              if(panel.type==='row'){section=String(panel.title||'Other panels');
                for(const child of panel.panels||[]){if(child.type!=='row')list.push({id:Number(child.id),title:String(child.title||'Untitled'),type:String(child.type||'unknown'),section});}
              }else list.push({id:Number(panel.id),title:String(panel.title||'Untitled'),type:String(panel.type||'unknown'),section});
            }
            return {ok:true,panels:list.slice(0,250)};
          }catch(e){return{ok:false,error:String(e?.message||e).slice(0,300)};}
        }});
        const answer=out?.[0]?.result;
        if(!answer?.ok)throw new Error(answer?.error||'Panel inspection unavailable.');
        const mapped=new Set(ALL_REPORT_ORDER.flatMap(id=>REPORTS[id].sourceIds));
        return {panels:answer.panels.map(p=>({...p,mapped:mapped.has(p.id)}))};
      }
      case 'CURRENT_GRAFANA_TAB':{
        // A full-page workspace is itself the active tab. Find the signed-in
        // dashboard explicitly instead of accidentally inspecting the workspace.
        const active=(await chrome.tabs.query({active:true,lastFocusedWindow:true}))[0];
        if(active?.url?.startsWith('https://grafana-apj.trafficpeak.live/')&&findMatchingURL(active.url,'db7ce6f6-d689-4976-89e5-ddf0b5401f97')){parseDashboardUrl(active.url);return {url:active.url};}
        const c=await config();const tabs=await chrome.tabs.query({url:'https://grafana-apj.trafficpeak.live/*'});
        const dashboards=tabs.filter(t=>t.id&&!t.discarded&&t.url?.startsWith('https://grafana-apj.trafficpeak.live/')&&findMatchingURL(t.url,'db7ce6f6-d689-4976-89e5-ddf0b5401f97'));
        if(!dashboards.length)throw new Error('Open your Grafana dashboard in another tab and sign in, then try again.');
        const preferred=(await chrome.storage.local.get('smartExportReturnGrafanaTabId')).smartExportReturnGrafanaTabId;
        const chosen=dashboards.find(t=>t.id===preferred)||dashboards.find(t=>t.url===c.dashboardUrl)||dashboards[0];
        parseDashboardUrl(chosen.url);
        await chrome.storage.local.set({smartExportReturnGrafanaTabId:chosen.id});
        return {url:chosen.url};
      }
      default: throw new Error('Unknown Smart Export command.');
    }
  })().then(data=>reply({ok:true,data})).catch(e=>reply({ok:false,error:cleanError(e)}));
  return true;
});
chrome.alarms.onAlarm.addListener(a=>{if(a.name===ALARM)automaticCheck().catch(e=>console.warn(cleanError(e)));});
async function ensureAlarm(){await chrome.alarms.create(ALARM,{delayInMinutes:1,periodInMinutes:60});}
chrome.runtime.onInstalled.addListener(()=>{ensureAlarm().catch(console.error);});
chrome.runtime.onStartup.addListener(()=>{ensureAlarm().then(automaticCheck).catch(console.error);});
// If Chrome cleared the alarm unexpectedly, recreate it when worker starts.
chrome.alarms.get(ALARM).then(a=>{if(!a)ensureAlarm();}).catch(()=>{});

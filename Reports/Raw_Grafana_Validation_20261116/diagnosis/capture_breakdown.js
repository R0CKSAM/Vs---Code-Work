// Run inside the existing signed-in Smart Export extension's DevTools console.
// Fixed read-only aggregate query; no log row identifiers or credentials returned.
(async()=>{
 const {parseDashboardUrl,FALLBACK_DATASOURCE_UID}=await import('./core.mjs');
 const {smartExportConfig:conf}=await chrome.storage.local.get('smartExportConfig');
 const spec=parseDashboardUrl(conf.dashboardUrl);
 if(spec.filters.length)throw Error('This raw audit expects an unfiltered source; clear filters explicitly before capture.');
 const tabs=await chrome.tabs.query({url:spec.origin+'/*'});
 const tab=tabs.find(t=>{try{return !t.discarded&&parseDashboardUrl(t.url).datasetKey===spec.datasetKey;}catch{return false;}});
 if(!tab)throw Error('No matching signed-in Grafana tab.');
 const fromMs=Date.parse('2026-11-15T18:30:00Z'),toMs=Date.parse('2026-11-16T18:30:00Z');
 const sql="SELECT reqHost AS host,toUnixTimestamp(toStartOfHour(reqTimeSec)) AS hour_epoch,endsWith(reqPath,'.ts') AS is_ts,count() AS requests,countIf(reqPath LIKE '%.ts' AND statusCode IN (200,206) AND extract(reqPath,'[-_](\\\\d+)\\\\.ts$') != '') AS ts_eligible,sumIf(bytes,reqPath LIKE '%.ts' AND statusCode IN (200,206)) AS video_bytes FROM Veto_Streamin.logs WHERE reqTimeSec >= toDateTime(1794767400,'UTC') AND reqTimeSec < toDateTime(1794853800,'UTC') GROUP BY host,hour_epoch,is_ts ORDER BY host,hour_epoch,is_ts SETTINGS hdx_query_max_execution_time=60";
 const [response]=await chrome.scripting.executeScript({target:{tabId:tab.id},world:'MAIN',args:[{uid:spec.uid,orgId:spec.orgId,sql,fromMs,toMs,fallback:FALLBACK_DATASOURCE_UID}],func:async p=>{
  try{
   if(location.origin!=='https://grafana-apj.trafficpeak.live'||!location.pathname.startsWith('/d/'+p.uid+'/'))throw Error('Wrong Grafana tab');
   const check=()=>{const u=new URL(location.href);if((u.searchParams.get('orgId')||'743')!==p.orgId||u.searchParams.getAll('var-filter').some(v=>v.trim()))throw Error('Grafana scope changed');};check();
   const dr=await fetch('/api/dashboards/uid/'+encodeURIComponent(p.uid),{credentials:'same-origin',headers:{'X-Grafana-Org-Id':p.orgId},signal:AbortSignal.timeout(15000)});if(!dr.ok)throw Error('Dashboard HTTP '+dr.status);const doc=await dr.json();
   const panels=(doc.dashboard?.panels||[]).flatMap(x=>[x,...(x.panels||[])]);
   const panel=panels.find(x=>x.id===14);if(!panel?.targets?.some(t=>t.rawSql?.includes('statusCode')))throw Error('Source segment panel changed; verify before capture');
   let ds=(panel.targets||[]).map(t=>t.datasource?.uid).find(x=>x&&!x.includes('${'));
   if(!ds)ds=(doc.dashboard?.templating?.list||[]).find(x=>x.type==='adhoc')?.datasource?.uid;
   if(!ds||ds.includes('${'))ds=p.fallback;
   check();const r=await fetch('/api/ds/query',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-Grafana-Org-Id':p.orgId},signal:AbortSignal.timeout(90000),body:JSON.stringify({queries:[{datasource:{type:'hydrolix-hydrolix-datasource',uid:ds},refId:'A',format:1,rawSql:p.sql,filters:[],intervalMs:60000,maxDataPoints:100000}],from:String(p.fromMs),to:String(p.toMs)})});const data=await r.json();if(!r.ok||data.results?.A?.error)throw Error(data.results?.A?.error||'Query HTTP '+r.status);
   return {ok:true,data};
  }catch(e){return {ok:false,error:String(e.message||e)};}
 }});
 window.rawBreakdownLive={schema:'veto-raw-grafana-window/v1',capturedAt:new Date().toISOString(),window:{fromUtc:new Date(fromMs).toISOString(),toUtcExclusive:new Date(toMs).toISOString(),label:'16 Nov full IST day'},sql,filters:[],response:response?.result};
 console.log('RAW_BREAKDOWN_READY '+JSON.stringify({ok:window.rawBreakdownLive.response?.ok,error:window.rawBreakdownLive.response?.error,groups:window.rawBreakdownLive.response?.data?.results?.A?.frames?.map(f=>f.data.values[0]?.length)}));
})()

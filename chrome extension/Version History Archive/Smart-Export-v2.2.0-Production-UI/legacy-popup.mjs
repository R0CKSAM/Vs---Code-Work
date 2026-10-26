import {DEFAULT_CONFIG,parseDashboardUrl,datesForLastCompleteDays,istToday} from './core.mjs';
import {REPORTS,REPORT_ORDER,rowsToCsv} from './reports.mjs';
import {allReportRows} from './report-db.mjs';
import {buildReportWorkbook} from './multi-xlsx.mjs';
const $=id=>document.getElementById(id);
let config={...DEFAULT_CONFIG,selectedReport:'executive'},working=false;
const send=(type,args={})=>new Promise((resolve,reject)=>chrome.runtime.sendMessage({type,...args},res=>{
 if(chrome.runtime.lastError)return reject(new Error(chrome.runtime.lastError.message));
 if(!res)return reject(new Error('Extension service worker is unavailable. Reload Smart Export.'));
 if(!res.ok)return reject(new Error(res.error||'Unknown export error.'));
 resolve(res.data);
}));
const msg=(value,kind='info')=>{const x=$('feedback');x.textContent=value;x.className='feedback '+(kind==='warning'?'warn':kind==='error'?'error':kind==='success'?'success':'');};
function busy(flag){working=!!flag;for(const id of ['useCurrent','syncNow','autoDaily','reportType','last7','last30'])$(id).disabled=working;$('syncLabel').textContent=working?'Fetching reports…':'Fetch & merge data';}
const stamp=ts=>{if(!ts)return 'Never';try{return new Date(ts).toLocaleString('en-IN',{dateStyle:'medium',timeStyle:'short',timeZone:'Asia/Kolkata'});}catch{return '—';}};
const preset=n=>{const r=datesForLastCompleteDays(n);$('dateFrom').value=r.from;$('dateTo').value=r.to;};
const activeReport=()=>String($('reportType').value);
function updateDescription(){const id=activeReport(),data=REPORTS[id];$('reportDescription').textContent=id==='executive'?'Six master tabs + definitions. Up to 31 completed IST days per fetch.':data.short+'. History is merged by date and group.';}
async function state(){
 try{
  const r=await send('STATE_V2');config={...DEFAULT_CONFIG,...r.config};
  if(document.activeElement!==$('dashboardUrl'))$('dashboardUrl').value=config.dashboardUrl;
  if(document.activeElement!==$('reportType'))$('reportType').value=REPORTS[config.selectedReport]?config.selectedReport:'executive';
  updateDescription();
  const id=activeReport(),types=id==='executive'?REPORT_ORDER:[id];
  const sum=(id==='executive')?types.map(t=>r.summaries[t]):[r.summaries[id]];
  const count=sum.reduce((n,a)=>n+(a?.rows||0),0);
  const dayCount=id==='executive'?(r.coverage?.uniqueDays||0):(r.summaries[id]?.days||0);
  const complete=REPORT_ORDER.filter(t=>r.summaries[t]?.rows>0).length;
  $('rowCount').textContent=count.toLocaleString('en-IN');$('dayCount').textContent=dayCount.toLocaleString('en-IN');$('variantCount').innerHTML=`${complete}<span class="slash">/6</span>`;
  const vals=types.map(t=>r.summaries[t]).filter(x=>x?.rows);
  $('rangeDetails').textContent=vals.length?`Stored history: ${vals.map(v=>v.from).sort()[0]} to ${vals.map(v=>v.to).sort().at(-1)} · ${id==='executive'?`${complete}/6 report types ready`:REPORTS[id].title}`:'No data saved for this report yet.';
  $('autoDaily').checked=!!config.enabled&&!!config.v2Mode&&config.autoReport===id;
  $('lastSynced').textContent=`Last sync: ${stamp(config.lastSuccessAt)} · ${config.enabled?`Daily job: ${config.v2Mode?REPORTS[config.autoReport]?.title||'Unknown':'Legacy GEO'}`:'Daily update is off'}`;
  $('downloadXlsx').disabled=!(id==='executive'?complete===6:!!r.summaries[id]?.rows);
  $('downloadCsv').disabled=id==='executive'||!r.summaries[id]?.rows;
  const chip=$('stateChip');chip.textContent=working||r.busy?'WORKING':config.enabled?(config.v2Mode?'DAILY ON':'V1 GEO ON'):'READY';chip.className='chip '+(working||r.busy?'working':config.enabled?'ok':'neutral');
  if(r.activity&&!working&&Date.now()-r.activity.time<4*60*1000)msg(r.activity.message,r.activity.kind);
 }catch(e){msg(e.message,'error');}
}
async function saveSettings(){const spec=parseDashboardUrl($('dashboardUrl').value.trim());await send('SAVE_V2',{dashboardUrl:spec.url,report:activeReport()});return spec;}
const download=(blob,name)=>{const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),45000);};
async function exportFile(type){
 try{
  const spec=parseDashboardUrl(config.dashboardUrl),datasets=await allReportRows(spec.datasetKey),report=activeReport();
  const period=istToday();
  if(type==='csv'){
   if(report==='executive')throw new Error('Choose one report type for CSV; the Executive workbook is Excel only.');
   if(!datasets[report]?.length)throw new Error('No saved records for this report.');
   download(new Blob([rowsToCsv(report,datasets[report])],{type:'text/csv;charset=utf-8'}),`Smart-Export-${report}-${period}.csv`);
  }else{
   const types=report==='executive'?REPORT_ORDER:[report];
   const allDates=types.flatMap(id=>(datasets[id]||[]).map(row=>row.date)).sort();
   const workbook=buildReportWorkbook(datasets,{report,from:allDates[0],to:allDates.at(-1)});
   download(workbook,`Smart-Export-${report}-${period}.xlsx`);
  }
  msg(`Exported ${REPORTS[report].title} as ${type.toUpperCase()}.`,'success');
 }catch(e){msg(e.message,'error');}
}
async function syncNow(){if(working)return;busy(true);try{
 await saveSettings();const report=activeReport(),from=$('dateFrom').value,to=$('dateTo').value;
 const results=await send('SYNC_V2',{report,from,to});
 msg(`Successfully updated ${results.rows.toLocaleString('en-IN')} records across ${results.reports} report type(s).`,'success');
 }catch(e){msg(e.message,'error');}finally{busy(false);await state();}}
async function changeSchedule(){const enable=$('autoDaily').checked;try{
 await saveSettings();await send('ENABLE_V2',{enabled:enable,report:activeReport()});
 msg(enable?`Scheduled daily refresh: ${REPORTS[activeReport()].title} at approximately 8 AM IST while Chrome and Grafana are running.`:'Daily refresh paused.','success');await state();
 }catch(e){$('autoDaily').checked=!enable;msg(e.message,'error');}}
async function init(){
 preset(7);await state();
 $('reportType').addEventListener('change',async()=>{updateDescription();try{
  await saveSettings();await state();
  if(config.enabled && !config.v2Mode)msg('Your previous v1 GEO daily job remains active until you enable a v2 schedule.','warning');
 }catch(e){msg(e.message,'error');}});
 $('useCurrent').addEventListener('click',async()=>{try{const r=await send('CURRENT_GRAFANA_TAB');$('dashboardUrl').value=r.url;await saveSettings();msg('Active Grafana dashboard selected.','success');await state();}catch(e){msg(e.message,'error');}});
 $('last7').addEventListener('click',()=>preset(7));$('last30').addEventListener('click',()=>preset(30));
 $('syncNow').addEventListener('click',syncNow);
 $('downloadXlsx').addEventListener('click',()=>exportFile('xlsx'));
 $('downloadCsv').addEventListener('click',()=>exportFile('csv'));
 $('autoDaily').addEventListener('change',changeSchedule);
 $('logs').addEventListener('click',async()=>{try{const d=await send('EXPORT_LOGS');download(new Blob([JSON.stringify({product:'Smart Export v2',exportedAt:new Date().toISOString(),logs:d.logs},null,2)],{type:'application/json'}),'Smart-Export-Errors.json');msg('Diagnostics downloaded. Review before sharing.','success');}catch(e){msg(e.message,'error');}});
 $('clearData').addEventListener('click',async()=>{if(!confirm('Delete the saved v2 report master? Download Excel first. Legacy v1 GEO data will remain.'))return;if(!confirm('Confirm permanent deletion of all v2 report types for this dashboard.'))return;try{await send('CLEAR_V2');await state();msg('The v2 master was cleared. The original v1 GEO master was not changed.','success');}catch(e){msg(e.message,'error');}});
 chrome.storage.onChanged.addListener(ch=>{if(ch.smartExportActivity||ch.smartExportConfig)state().catch(()=>{});});
}
init().catch(e=>msg(e.message,'error'));

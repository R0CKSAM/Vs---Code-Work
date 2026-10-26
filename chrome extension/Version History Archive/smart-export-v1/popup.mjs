import {DEFAULT_CONFIG,DEFAULT_DASHBOARD_URL,parseDashboardUrl,datesForLastCompleteDays,validYMD,summarize,istToday} from './core.mjs';
import {readDataset} from './database.mjs';
import {toCSV} from './core.mjs';
import {makeWorkbook} from './xlsx.mjs';
const $=id=>document.getElementById(id);
let config={...DEFAULT_CONFIG};let isWorking=false;
function message(text,kind='info'){
  const el=$('feedback');el.className='feedback'+(kind==='error'?' error':kind==='success'?' success':kind==='warning'?' warn':'');el.textContent=text;
}
function setLoading(flag){isWorking=flag;$('syncNow').disabled=flag;$('syncNow').querySelector('span:not(.button-tail)').textContent=flag?'Fetching GEO data…':'Fetch & merge data';$('useCurrent').disabled=flag;$('autoDaily').disabled=flag;}
function send(type,payload={}){return new Promise((resolve,reject)=>{
  chrome.runtime.sendMessage({type,...payload},response=>{
    if(chrome.runtime.lastError)return reject(new Error(chrome.runtime.lastError.message));
    if(!response)return reject(new Error('Extension worker did not respond. Reload Smart Export in Chrome.'));
    if(!response.ok)return reject(new Error(response.error||'Unknown extension error'));
    resolve(response.data);
  });
});}
function timestamp(ts){if(!ts)return '—';try{return new Date(ts).toLocaleString('en-IN',{timeZone:'Asia/Kolkata',dateStyle:'medium',timeStyle:'short'});}catch{return'—';}}
async function refresh(){
  let info;try{info=await send('STATE');}catch(e){message(e.message,'error');return;}
  config={...DEFAULT_CONFIG,...info.config};
  if(document.activeElement!==$('dashboardUrl'))$('dashboardUrl').value=config.dashboardUrl;
  $('autoDaily').checked=!!config.enabled;
  $('rowCount').textContent=(info.summary.rows||0).toLocaleString('en-IN');
  $('dayCount').textContent=(info.summary.days||0).toLocaleString('en-IN');
  $('rangeDetails').textContent=info.summary.rows ? `${info.summary.from} to ${info.summary.to} · Master stored locally` : 'No data imported yet. Start with historical export.';
  $('lastSynced').textContent=`Last successful sync: ${timestamp(config.lastSuccessAt)} · ${config.enabled?'Daily update ON':'Daily update OFF'}`;
  $('downloadXlsx').disabled=!(info.summary.rows>0);
  $('downloadCsv').disabled=!(info.summary.rows>0);
  const chip=$('stateChip');chip.textContent=isWorking?'WORKING':config.enabled?'DAILY ON':'READY';chip.className='chip '+(isWorking?'working':config.enabled?'ok':'neutral');
  const event=info.activity;
  if(event && !isWorking && !(Date.now()-event.time>5*60_000)) message(event.message,event.kind);
}
function selectedRange(){return {from:$('dateFrom').value,to:$('dateTo').value};}
async function saveSource(){
  const spec=parseDashboardUrl($('dashboardUrl').value.trim());
  await send('SAVE_SETTINGS',{dashboardUrl:spec.url,enabled:$('autoDaily').checked});
  return spec;
}
function loadPreset(n){const r=datesForLastCompleteDays(n);$('dateFrom').value=r.from;$('dateTo').value=r.to;}
function download(blob,filename){
  const url=URL.createObjectURL(blob),a=document.createElement('a');
  a.href=url;a.download=filename;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),45_000);
}
async function getCurrentRows(){
  const c=config;const spec=parseDashboardUrl(c.dashboardUrl);
  const rows=await readDataset(spec.datasetKey);
  if(!rows.length)throw new Error('Master dataset is empty. Fetch a date range first.');
  return rows;
}
async function exportFile(format){
  try{
    const rows=await getCurrentRows();const fileDate=istToday();
    if(format==='csv')download(new Blob([toCSV(rows)],{type:'text/csv;charset=utf-8'}),`Smart-Export-GEO-${fileDate}.csv`);
    else download(makeWorkbook(rows),`Smart-Export-GEO-${fileDate}.xlsx`);
    message(`Exported the latest master: ${rows.length.toLocaleString('en-IN')} records.`, 'success');
  }catch(e){message(e.message,'error');}
}
async function runSync(){
  if(isWorking)return;
  setLoading(true);
  try{
    await saveSource(); const {from,to}=selectedRange();
    const result=await send('SYNC',{from,to});
    message(result.empty?'Grafana returned no GEO rows; nothing changed.':`Merged ${result.rows.toLocaleString('en-IN')} GEO rows from ${result.days} dates.`,result.empty?'warning':'success');
  }catch(e){message(e.message,'error');}
  finally{setLoading(false);await refresh();}
}
function listen(id,fn){$(id).addEventListener('click',fn);}
async function load(){
  loadPreset(7);
  await refresh();
  listen('last7',()=>loadPreset(7));
  listen('last30',()=>loadPreset(30));
  listen('useCurrent',async()=>{
    try{
      const t=await send('CURRENT_GRAFANA_TAB');$('dashboardUrl').value=t.url;
      await saveSource();message('Grafana dashboard selected. Choose dates and fetch.','success');await refresh();
    }catch(e){message(e.message,'error');}
  });
  listen('syncNow',runSync);
  $('autoDaily').addEventListener('change',async()=>{
    const checked=$('autoDaily').checked;
    try{await saveSource();await send('ENABLE',{enabled:checked});
      message(checked?'Daily sync enabled for 8:00 AM IST while Chrome and Grafana are open.':'Daily sync paused.', 'success');await refresh();
    }catch(e){$('autoDaily').checked=!checked;message(e.message,'error');}
  });
  listen('downloadXlsx',()=>exportFile('xlsx'));listen('downloadCsv',()=>exportFile('csv'));
  listen('logs',async()=>{
    try{const result=await send('EXPORT_LOGS');download(new Blob([JSON.stringify({product:'Smart Export',generatedAt:new Date().toISOString(),logs:result.logs},null,2)],{type:'application/json'}),'Smart-Export-Diagnostics.json');}
    catch(e){message(e.message,'error');}
  });
  listen('clearData',async()=>{
    if(!confirm('Permanently clear this dashboard’s stored GEO master rows? Export Excel first if you need a backup.'))return;
    if(!confirm('Confirm again: all locally stored master GEO rows for this dashboard will be erased.'))return;
    try{await send('CLEAR_DATA');message('Local master data erased.','success');await refresh();}catch(e){message(e.message,'error');}
  });
  chrome.storage.onChanged.addListener(changes=>{if(changes.smartExportActivity||changes.smartExportConfig){refresh().catch(()=>{});}});
}
load().catch(e=>message(e.message,'error'));

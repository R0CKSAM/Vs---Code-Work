/* Smart Export Parameter Studio v2.5.1.
 * This UI is an adapter to the existing certified Grafana export engine.
 * Selection and fetching go through SmartExportBridge; it never scrapes labels,
 * loops through hidden checkboxes, or assumes a request completed after a timer.
 */
import { REPORT_ORDER, REPORTS } from './reports.mjs';
import { GROUPS, DETAILS, normalizeSelection } from './metric-catalog.mjs';
const $ = id => document.getElementById(id);
const TABS = [
  ['kpis','Overview'], ['channel','Channels'], ['content','Content'],
  ['geo','Locations'], ['devices','Devices'], ['traffic','Streaming']
];
const state = {
  bridge:null, category:'kpis', search:'', selection:{}, breakdown:'day',
  working:false, connected:false, source:'', ready:false, selectedFormat:'xlsx'
};
const timeZone='Asia/Kolkata';
const validDate = text => {
 if(!/^\d{4}-\d{2}-\d{2}$/.test(text))return false;
 const date=new Date(`${text}T12:00:00Z`);
 return !Number.isNaN(date.getTime())&&date.toISOString().slice(0,10)===text;
};
const istToday = () => new Intl.DateTimeFormat('en-CA', {
  timeZone, year:'numeric', month:'2-digit', day:'2-digit'
}).format(new Date());
function dayOffset(ymd,days){const d = new Date(`${ymd}T12:00:00Z`);d.setUTCDate(d.getUTCDate()+days);return d.toISOString().slice(0,10)}
const countSelected = () => Object.values(state.selection).reduce((n,fields)=>n+fields.length,0);
const selectedReportIds = () => REPORT_ORDER.filter(id=>(state.selection[id]||[]).length);
function setError(message){const node=$('psError');node.textContent=String(message);node.hidden=false;node.scrollIntoView({block:'nearest'});}
function clearError(){$('psError').hidden=true;$('psError').textContent='';}
function reportBreakdownAllowed(name){
 if(name==='day')return true;
 return (state.selection[({channel:'channel',country:'geo',platform:'devices'})[name]]||[]).length>0;
}
function validationMessage(){
 const from=$('psFrom').value,to=$('psTo').value,today=istToday();
 if(!validDate(from)||!validDate(to))return 'Select valid From and To dates.';
 if(from>to)return 'From date must be on or before To date.';
 if(to>=today)return 'Only completed IST days can be exported. Choose yesterday or earlier.';
 const days=Math.round((Date.parse(`${to}T12:00:00Z`)-Date.parse(`${from}T12:00:00Z`))/86400000)+1;
 if(days>31)return 'Select a maximum of 31 calendar days per fetch.';
 if(!countSelected())return 'Select at least one supported parameter.';
 if(!reportBreakdownAllowed(state.breakdown))return 'This breakdown needs the matching report category.';
 if(state.selectedFormat==='csv' && selectedReportIds().length!==1)return 'CSV supports one report category. Choose Excel for multiple categories.';
 if(!state.source)return 'Open your Grafana dashboard and choose Use open Grafana tab.';
 if(!state.connected)return 'Keep your Grafana dashboard tab open and sign in before fetching.';
 return '';
}
function updateValidation(){
 const msg=validationMessage();
 $('psValidation').textContent=msg;
 const blocked=!!msg||state.working||!state.ready;
 $('psFetch').disabled=blocked;$('psDialogFetch').disabled=blocked;
 $('psFetch').textContent=state.working?'Fetching Grafana data…':'Get data →';
 $('psDialogFetch').textContent=state.working?'Fetching…':'Get data →';
 $('psBadge').textContent=`${countSelected()} parameter${countSelected()===1?'':'s'}`;
 const from=$('psFrom').value,to=$('psTo').value;
 $('psBottomSummary').textContent=`${countSelected()} selected · ${from||'—'} → ${to||'—'} · IST`;
 $('psDates').textContent=`${from||'—'} → ${to||'—'}`;
 $('psGroup').textContent=state.breakdown==='day'?'By day':`By ${state.breakdown} (where supported)`;
 for(const b of document.querySelectorAll('.ps-breakdown-row button')){
  b.disabled=state.working||(!reportBreakdownAllowed(b.dataset.break)&&b.dataset.break!=='day');
  b.classList.toggle('on',b.dataset.break===state.breakdown);
  b.setAttribute('aria-pressed',String(b.dataset.break===state.breakdown));
 }
 for(const b of document.querySelectorAll('.ps-presets button')){
  b.setAttribute('aria-pressed',String(b.classList.contains('active')));
 }
 const resultBtn=$('psDownloadChosen');if(resultBtn){
  const existing=$('downloadCsv'),xlsx=$('downloadXlsx');
  const exportTarget=state.selectedFormat==='csv'?existing:xlsx;
  resultBtn.disabled=state.working||!exportTarget||exportTarget.disabled;
  resultBtn.textContent=state.selectedFormat==='csv'?'Download selected CSV ↓':'Download selected Excel ↓';
 }
}
function visibleFields(){
 const text=state.search.toLowerCase().trim();const ids=text?REPORT_ORDER:[state.category];
 const result=[];
 for(const id of ids){
  for(const field of REPORTS[id].metrics){
   const label=DETAILS[field]?.label||field,help=DETAILS[field]?.help||REPORTS[id].short;
   if(!text||`${label} ${help} ${GROUPS[id].title}`.toLowerCase().includes(text))result.push({id,field,label,help});
  }
 }
 return result;
}
function updateCards(){
 document.querySelectorAll('.ps-metric[data-report]').forEach(button=>{
  const chosen=(state.selection[button.dataset.report]||[]).includes(button.dataset.field);
  button.classList.toggle('selected',chosen);
  button.setAttribute('aria-checked',String(chosen));
  const mark=button.querySelector('.ps-check');if(mark)mark.textContent=chosen?'✓':'';
  button.disabled=state.working;
 });
}
function renderTabs(){
 const host=$('psTabs');host.replaceChildren();
 for(const [id,title] of TABS){
  const b=document.createElement('button');b.type='button';b.textContent=title;
  b.dataset.category=id;b.setAttribute('role','tab');
  b.setAttribute('aria-selected',String(id===state.category));b.tabIndex=id===state.category?0:-1;
  b.onclick=()=>{state.category=id;state.search='';$('psSearch').value='';renderTabs();renderCards();};
  b.onkeydown=e=>{
   if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;
   e.preventDefault();let i=TABS.findIndex(([x])=>x===id);
   i=e.key==='Home'?0:e.key==='End'?TABS.length-1:(i+(e.key==='ArrowRight'?1:-1)+TABS.length)%TABS.length;
   state.category=TABS[i][0];state.search='';$('psSearch').value='';renderTabs();renderCards();
   host.querySelectorAll('button')[i].focus();
  };
  host.append(b);
 }
}
function renderCards(){
 const host=$('psMetrics');host.replaceChildren();
 const list=visibleFields();
 if(!list.length){const none=document.createElement('div');none.className='ps-empty';none.textContent='No matching metrics. Try searching for users, sessions, playtime or channels.';host.append(none);return;}
 for(const item of list){
  const chosen=(state.selection[item.id]||[]).includes(item.field);
  const b=document.createElement('button');b.className='ps-metric'+(chosen?' selected':'');b.type='button';
  b.dataset.report=item.id;b.dataset.field=item.field;
  b.setAttribute('role','checkbox');b.setAttribute('aria-checked',String(chosen));
  b.setAttribute('aria-label',`${item.label}, ${GROUPS[item.id].title}`);
  const top=document.createElement('span');top.className='ps-metric-top';
  const title=document.createElement('span');title.className='ps-metric-title';title.textContent=item.label;
  const check=document.createElement('span');check.className='ps-check';check.textContent=chosen?'✓':'';check.setAttribute('aria-hidden','true');
  top.append(title,check);
  const hint=document.createElement('span');hint.className='ps-metric-help';hint.textContent=item.help;
  b.append(top,hint);
  b.onclick=()=>toggleMetric(item.id,item.field);
  b.disabled=state.working;
  host.append(b);
 }
}
function renderSelection(){
 const host=$('psSelected');host.replaceChildren();
 const labelCounts={};for(const id of REPORT_ORDER)for(const field of state.selection[id]||[]){
  const key=DETAILS[field]?.label||field;labelCounts[key]=(labelCounts[key]||0)+1;
 }
 for(const id of REPORT_ORDER){
  for(const field of state.selection[id]||[]){
   const name=DETAILS[field]?.label||field;
   const row=document.createElement('div');row.className='ps-selected-row';
   const label=document.createElement('span');label.textContent=labelCounts[name]>1?`${name} · ${GROUPS[id].title}`:name;
   const del=document.createElement('button');del.type='button';del.textContent='×';
   del.disabled=state.working;del.title=`Remove ${name}`;del.setAttribute('aria-label',del.title);
   del.onclick=()=>toggleMetric(id,field);row.append(label,del);host.append(row);
  }
 }
 if(!host.children.length){const blank=document.createElement('div');blank.className='ps-empty';blank.textContent='Select a metric from the cards to build your report.';host.append(blank);}
 updateValidation();
}
function updateStatus(text,connected=false){state.connected=connected;const b=$('psConnection');b.textContent=`● ${text}`;b.classList.toggle('connected',connected);}
async function setSelection(next){
 if(!state.bridge?.ready||state.working)return;
 const old=state.selection;
 try{
  const clean=normalizeSelection(next,{allowEmpty:true});
  state.selection=clean;
  if(!reportBreakdownAllowed(state.breakdown))state.breakdown='day';
  updateCards();renderSelection();clearError();
  await state.bridge.setSelection(clean);
 }catch(e){state.selection=old;updateCards();renderSelection();setError(`Could not save selection: ${e.message}`);}
}
async function toggleMetric(report,metric){
 const next=normalizeSelection(state.selection,{allowEmpty:true});
 const fields=new Set(next[report]||[]);if(fields.has(metric))fields.delete(metric);else fields.add(metric);
 if(fields.size)next[report]=REPORTS[report].metrics.filter(x=>fields.has(x));else delete next[report];
 await setSelection(next);
}
function setRange(type){
 if(type==='custom'){$('psFrom').focus();return;}
 if(type==='today')return;
 const today=istToday(),n=type==='yesterday'?1:Number(type);
 const to=dayOffset(today,-1),from=dayOffset(today,-n);
 $('psFrom').value=from;$('psTo').value=to;
 for(const b of document.querySelectorAll('.ps-presets button'))b.classList.toggle('active',b.dataset.date===String(type));
 state.bridge?.setDates({from,to});updateValidation();clearError();
}
function dateChanged(){
 for(const b of document.querySelectorAll('.ps-presets button'))b.classList.toggle('active',b.dataset.date==='custom');
 state.bridge?.setDates({from:$('psFrom').value,to:$('psTo').value});
 updateValidation();clearError();
}
function syncFromEngine(){
 if(!state.bridge?.ready||state.working)return;
 const latest=normalizeSelection(state.bridge.getSelection(),{allowEmpty:true});
 if(JSON.stringify(latest)!==JSON.stringify(state.selection)){state.selection=latest;renderCards();renderSelection();}
 const dates=state.bridge.getDates();
 if(dates.from&&dates.to){$('psFrom').value=dates.from;$('psTo').value=dates.to;}
 state.source=state.bridge.getDashboardUrl()||state.source;updateValidation();
}
function syncNavigation(){
 let active='build';for(const key of ['build','results','automation']){
  if(!$('view-'+key).hidden){active=key;break;}
 }
 for(const b of document.querySelectorAll('.ps-navigation button')){
  b.setAttribute('aria-pressed',String(b.dataset.screen===active));
 }
 if(active==='build')syncFromEngine();
}
async function linkGrafana(){
 try{const url=await state.bridge.useGrafana();state.source=url;updateStatus('Grafana tab ready',true);clearError();updateValidation();}
 catch(e){state.source='';updateStatus('Open Grafana tab',false);updateValidation();setError(e.message);}
}
async function verifyGrafana(){
 if(!state.ready)return;
 try{
  const result=await new Promise((resolve,reject)=>chrome.runtime.sendMessage({type:'CURRENT_GRAFANA_TAB'},r=>{
   if(chrome.runtime.lastError)return reject(new Error(chrome.runtime.lastError.message));
   if(!r?.ok)return reject(new Error(r?.error||'Grafana tab unavailable.'));
   resolve(r.data);
  }));
  updateStatus('Grafana tab ready',true);
  if(!state.source){state.source=await state.bridge.useGrafana().catch(()=>result.url);}
 }catch{
  updateStatus(state.source?'Saved Grafana source':'Open Grafana tab',false);
 }
 updateValidation();
}
async function fetchData(){
 if(state.working||!state.ready||!state.bridge)return;
 const msg=validationMessage();if(msg){setError(msg);updateValidation();return;}
 state.working=true;clearError();updateCards();renderSelection();updateValidation();
 try{
  const success=await state.bridge.fetch();
  if(success){$('psDialog').close?.();state.bridge.showView('results');syncNavigation();}
  else {const underlying=$('feedback')?.textContent||'Grafana did not complete this request.';setError(underlying);}
 }catch(e){setError(e.message);}
 finally{state.working=false;updateCards();renderSelection();updateValidation();}
}
function previewSelection(){
 const lines=[
  `Date range: ${$('psFrom').value} to ${$('psTo').value}`,
  `Timezone: ${timeZone}`,
  `Output: ${state.selectedFormat==='csv'?'CSV':'Excel workbook'}`,
  `Breakdown: ${state.breakdown}`,
  '',`Selected metrics (${countSelected()}):`
 ];
 for(const id of selectedReportIds()){
  lines.push('',`${GROUPS[id].title} — separate report tab`);
  for(const field of state.selection[id]||[])lines.push(`  • ${DETAILS[field]?.label||field}`);
 }
 lines.push('', 'Distinct daily users, IPs and sessions are never summed into range-wide unique counts.',
  'Only certified Grafana metric groups are requested.');
 $('psPreviewBody').textContent=lines.join('\n');
 $('psDialog').showModal();
}
function addEvents(){
 $('psSearch').addEventListener('input',e=>{state.search=e.target.value;renderCards();});
 $('psSelectAll').addEventListener('click',()=>{
  const next=normalizeSelection(state.selection,{allowEmpty:true});
  for(const {id,field} of visibleFields()){
   const fields=new Set(next[id]||[]);fields.add(field);next[id]=REPORTS[id].metrics.filter(x=>fields.has(x));
  }
  setSelection(next);
 });
 $('psClear').addEventListener('click',()=>setSelection({}));
 $('psFrom').addEventListener('change',dateChanged);$('psTo').addEventListener('change',dateChanged);
 for(const b of document.querySelectorAll('.ps-presets button'))b.addEventListener('click',()=>setRange(b.dataset.date));
 for(const b of document.querySelectorAll('.ps-breakdown-row button'))b.addEventListener('click',()=>{
  if(!b.disabled){state.breakdown=b.dataset.break;updateValidation();}
 });
 $('psFormat').addEventListener('change',e=>{state.selectedFormat=e.target.value;updateValidation();});
 $('psUseGrafana').addEventListener('click',linkGrafana);
 $('psOpenGrafana').addEventListener('click',()=>state.bridge.backGrafana());
 $('psPreview').addEventListener('click',previewSelection);
 $('psClose').addEventListener('click',()=>$('psDialog').close());
 $('psFetch').addEventListener('click',fetchData);$('psDialogFetch').addEventListener('click',fetchData);
 $('psDownloadChosen')?.addEventListener('click',()=>state.bridge.export(state.selectedFormat));
 for(const b of document.querySelectorAll('.ps-navigation button'))b.addEventListener('click',()=>{
  state.bridge?.showView(b.dataset.screen);syncNavigation();
 });
 for(const id of ['build','results','automation'])new MutationObserver(syncNavigation)
  .observe($('view-'+id),{attributes:true,attributeFilter:['hidden']});
}
async function initialize(){
 const bridge=window.SmartExportBridge;
 if(!bridge?.ready)return;
 state.bridge=bridge;state.ready=true;
 state.selection=normalizeSelection(bridge.getSelection(),{allowEmpty:true});
 const dates=bridge.getDates();
 $('psFrom').value=dates.from||'';$('psTo').value=dates.to||'';
 state.source=bridge.getDashboardUrl()||'';
 addEvents();renderTabs();renderCards();renderSelection();
 for(const b of document.querySelectorAll('.ps-presets button')){
  if(b.dataset.date==='today'){b.disabled=true;b.title='This exporter supports completed calendar days only.';}
 }
 const today=istToday(),last7start=dayOffset(today,-7),last7end=dayOffset(today,-1);
 if(dates.from===last7start&&dates.to===last7end){
  document.querySelector('[data-date="7"]').classList.add('active');
 }
 syncNavigation();updateStatus('Checking Grafana tab');
 await verifyGrafana();
}
// The original script runs first; wait only for the explicit ready signal.
if(window.SmartExportBridge?.ready){initialize();}
else{
 window.addEventListener('smart-export-ready',initialize,{once:true});
 window.addEventListener('smart-export-error',()=>setError('Smart Export could not load its reporting engine. Reload the extension.'),{once:true});
}

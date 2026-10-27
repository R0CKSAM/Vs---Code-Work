/* Smart Export v2.6 — Grafana-ordered, honest metric selector.
 * No added data endpoint: this controls the existing certified report engine.
 */
import {REPORT_ORDER, REPORTS} from './reports.mjs';
import {DETAILS, normalizeSelection} from './metric-catalog.mjs';
import {datesForLastCompleteDays, istToday, validYMD} from './core.mjs';
const $ = id => document.getElementById(id);
const GROUPS = [
 {id:'kpis',title:'Session and Users Stats',description:'Audience, sessions, views, estimated playtime and bandwidth.'},
 {id:'traffic',title:'Users, Sessions & Views — Time Series',description:'Hourly data derived from the dashboard’s traffic series.'},
 {id:'channel',title:'Viewership Trend · Playtime by Channel',description:'Compare channels across the selected dates.'},
 {id:'content',title:'Popular Content',description:'Content-title views, sessions and audience estimates.'},
 {id:'geo',title:'Playtime · GEO',description:'Daily location-level estimated playtime.'},
 {id:'devices',title:'Playtime · Devices and OS',description:'Platform and operating-system audience estimates.'},
];
const FRIENDLY={
 unique_devices:'Total users (Device ID)', unique_ips:'Total users (Unique IP)',
 session_ids:'Total sessions (Session ID)',ip_ua_sessions:'Sessions (IP + User Agent)',
 manifest_views:'Total views (manifest requests)',playtime_minutes:'Estimated playtime (minutes)',
 bandwidth_bytes:'Video bandwidth (bytes)'
};
const $groups = () => GROUPS.filter(x => REPORTS[x.id]);
const state={bridge:null,working:false,connected:false,source:'',selection:{},search:'',format:'xlsx',initialized:false,
 expanded:new Set(['kpis','traffic']),verifiedSnapshot:null};
const OUTPUT_KEY='smartExportExportFormat_v26';
const DATE_KEY='smartExportDateRange_v26';
const snapshot=()=>JSON.stringify({from:$('gxFrom').value,to:$('gxTo').value,selection:state.selection,source:state.source});
const validDate = v => typeof v==='string'&&validYMD(v);
const count=()=>Object.values(state.selection).reduce((n,v)=>n+v.length,0);
const reportsSelected=()=>REPORT_ORDER.filter(id=>(state.selection[id]||[]).length);
const dateDays=()=>{const a=$('gxFrom').value,b=$('gxTo').value;
 if(!validDate(a)||!validDate(b))return 0;return Math.round((Date.parse(b+'T12:00:00Z')-Date.parse(a+'T12:00:00Z'))/86400000)+1;};
function warn(message){const node=$('gxError');node.textContent=String(message);node.hidden=false;}
function clearWarn(){$('gxError').hidden=true;$('gxError').textContent='';}
function formatMessage(){return state.format==='xlsx'?'Excel workbook · a sheet per report':'Individual CSVs · ZIP file';}
function validate(){
 if(!state.initialized||!state.bridge?.ready)return 'Loading reporting engine…';
 if(!validDate($('gxFrom').value)||!validDate($('gxTo').value))return 'Select valid start and end dates.';
 if(dateDays()<1)return 'The start date must not be after the end date.';
 if(dateDays()>31)return 'Select a maximum of 31 completed calendar days per request.';
 if($('gxTo').value>=istToday())return 'Use completed calendar days only (yesterday or earlier).';
 if(!count())return 'Select at least one parameter.';
 if(!state.source||!state.connected)return 'Open your signed-in Grafana dashboard, then choose Connect Grafana.';
 return '';
}
function setConnected(connected,message){state.connected=connected;
 const target=$('gxConnection');target.textContent=(connected?'● ':'○ ')+message;
 target.classList.toggle('is-connected',connected);target.title=connected?'Grafana tab detected. Click to check again.':'Click to connect an open Grafana tab.';
 refreshActions();}
function updateChecks(){
 document.querySelectorAll('.gx-metric input[type=checkbox]').forEach(box=>{
  const selected=(state.selection[box.dataset.report]||[]).includes(box.dataset.field);
  box.checked=selected;box.closest('.gx-metric')?.classList.toggle('is-selected',selected);box.disabled=state.working;
 });
 for(const g of GROUPS){
  const el=document.querySelector(`[data-group-count="${g.id}"]`);
  if(el)el.textContent=(state.selection[g.id]||[]).length+' selected';
 }
 refreshActions();
}
function refreshActions(){
 const msg=validate();const num=count();const groups=reportsSelected().length;
 $('gxCount').textContent=`${num} parameter${num===1?'':'s'} · ${groups} section${groups===1?'':'s'} · ${dateDays()||'—'} day${dateDays()===1?'':'s'} (IST)`;
 $('gxFetch').disabled=!!msg||state.working;
 $('gxFetch').innerHTML=state.working?'Fetching Grafana data…':'Get data <span aria-hidden="true">→</span>';
 for(const btn of ['gxSelectVisible','gxClear'])$(btn).disabled=state.working;
 for(const input of ['gxFrom','gxTo','gxSearch'])$(input).disabled=state.working;
 for(const btn of document.querySelectorAll('.gx-presets button'))btn.disabled=state.working;
 for(const input of document.querySelectorAll('input[name="gxFormat"]'))input.disabled=state.working;
 // Date/configuration warnings shown only once user requests data, not at startup.
 const output=$('gxDownload');
 if(output){const ready=!$('downloadXlsx')?.disabled;
  output.disabled=state.working||!ready||state.verifiedSnapshot!==snapshot();
  output.textContent=state.format==='xlsx'?'Download Excel ↓':'Download CSV files ↓';
 }
}
function fieldMatches(id,field){const q=state.search.toLocaleLowerCase().trim();
 if(!q)return true;const g=GROUPS.find(x=>x.id===id);
 return [g?.title,g?.description,DETAILS[field]?.label,FRIENDLY[field],DETAILS[field]?.help].some(v=>String(v||'').toLocaleLowerCase().includes(q));
}
function renderSections(){
 const container=$('gxSections');const saved=new Map([...container.querySelectorAll('details')].map(x=>[x.dataset.group,x.open]));
 const host=document.createDocumentFragment();let shown=0;
 for(const [n,g] of $groups().entries()){
  const metrics=REPORTS[g.id].metrics.filter(field=>fieldMatches(g.id,field));
  if(!metrics.length)continue;shown+=metrics.length;
  const block=document.createElement('details');block.className='gx-section';block.dataset.group=g.id;
  block.open=state.search.trim()?true:(saved.has(g.id)?saved.get(g.id):state.expanded.has(g.id));
  const sum=document.createElement('summary');sum.className='gx-section-summary';
  const number=document.createElement('span');number.className='gx-section-number';number.textContent=String(n+1).padStart(2,'0');
  const titleBox=document.createElement('span');titleBox.className='gx-section-copy';
  const title=document.createElement('strong');title.textContent=g.title;
  const desc=document.createElement('small');desc.textContent=g.description;titleBox.append(title,desc);
  const selected=document.createElement('span');selected.className='gx-section-count';selected.dataset.groupCount=g.id;
  selected.textContent=(state.selection[g.id]||[]).length+' selected';
  const chevron=document.createElement('span');chevron.className='gx-chevron';chevron.setAttribute('aria-hidden','true');
  sum.append(number,titleBox,selected,chevron);
  const grid=document.createElement('div');grid.className='gx-metric-grid';
  for(const field of metrics){
   const label=document.createElement('label');label.className='gx-metric';
   const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.dataset.report=g.id;checkbox.dataset.field=field;
   checkbox.checked=(state.selection[g.id]||[]).includes(field);checkbox.disabled=state.working;
   const copy=document.createElement('span');copy.className='gx-metric-copy';
   const metricTitle=document.createElement('strong');metricTitle.textContent=FRIENDLY[field]||DETAILS[field]?.label||field;
   const help=document.createElement('small');help.textContent=DETAILS[field]?.help||'';
   copy.append(metricTitle,help);label.append(checkbox,copy);
   label.classList.toggle('is-selected',checkbox.checked);label.title=DETAILS[field]?.help||'';
   checkbox.addEventListener('change',()=>toggleMetric(g.id,field,checkbox.checked));grid.append(label);
  }
  block.append(sum,grid);block.addEventListener('toggle',()=>{
   if(!state.search.trim()) {if(block.open)state.expanded.add(g.id);else state.expanded.delete(g.id);}
  });host.append(block);
 }
 container.replaceChildren(host);
 if(!shown){const p=document.createElement('p');p.className='gx-no-match';p.textContent='No matching parameters. Try “users”, “playtime”, “content”, or “device”.';container.append(p);}
 refreshActions();
}
async function updateSelection(next){
 if(!state.bridge?.ready||state.working)return;
 const old=state.selection;
 try{
  const clean=normalizeSelection(next,{allowEmpty:true});state.selection=clean;state.verifiedSnapshot=null;updateChecks();clearWarn();
  await state.bridge.setSelection(clean);
 }catch(e){state.selection=old;updateChecks();warn(`Selection could not be saved: ${e.message}`);}
}
async function toggleMetric(id,field,on){
 const next=normalizeSelection(state.selection,{allowEmpty:true});const set=new Set(next[id]||[]);
 if(on)set.add(field);else set.delete(field);
 if(set.size)next[id]=REPORTS[id].metrics.filter(x=>set.has(x));else delete next[id];
 await updateSelection(next);
}
function setDates(from,to){
 $('gxFrom').value=from;$('gxTo').value=to;state.verifiedSnapshot=null;state.bridge?.setDates({from,to});
 if(validDate(from)&&validDate(to))chrome.storage.local.set({[DATE_KEY]:{from,to}}).catch(()=>{});
 const presets= [7,30].map(n=>[n,datesForLastCompleteDays(n)]);
 for(const btn of document.querySelectorAll('.gx-presets button')){
  const key=btn.dataset.range;let on=key==='yesterday'&&from===datesForLastCompleteDays(1).from&&to===datesForLastCompleteDays(1).to;
  for(const [n,v] of presets)if(key===String(n)&&v.from===from&&v.to===to)on=true;
  btn.classList.toggle('is-active',on);btn.setAttribute('aria-pressed',String(on));
 }
 clearWarn();refreshActions();
}
async function connectGrafana(){
 try{
  const url=await state.bridge.useGrafana();state.source=url;state.verifiedSnapshot=null;
  setConnected(true,'Grafana connected');clearWarn();
 }catch(e){setConnected(false,'Connect Grafana');warn(e.message);}
}
async function testConnection(){
 try{
  const res=await new Promise((resolve,reject)=>chrome.runtime.sendMessage({type:'CURRENT_GRAFANA_TAB'},r=>{
   if(chrome.runtime.lastError)return reject(new Error(chrome.runtime.lastError.message));
   if(!r?.ok)return reject(new Error(r?.error||'No Grafana tab found.'));
   resolve(r.data);
  }));
  // Use the actual open Grafana tab, not a stale saved URL, before reporting connected.
  if(res?.url&&res.url!==state.source){state.source=await state.bridge.useGrafana();state.verifiedSnapshot=null;}
  setConnected(true,'Grafana connected');
 }catch{setConnected(false,'Connect Grafana');}
}
async function fetchData(){
 if(state.working||!state.bridge?.ready)return;
 const message=validate();if(message){warn(message);return;}
 state.working=true;clearWarn();updateChecks();
 try{
  const success=await state.bridge.fetch();
  if(success){state.verifiedSnapshot=snapshot();state.bridge.showView('results');syncNavigation();refreshActions();}
  else warn($('feedback')?.textContent||'Grafana did not complete the request. Open Settings → Troubleshooting for details.');
 }catch(e){warn(e.message);}
 finally{state.working=false;updateChecks();}
}
function syncNavigation(){
 let view='build';for(const key of ['build','results','automation'])if(!$('view-'+key).hidden){view=key;break;}
 for(const nav of document.querySelectorAll('.ps-navigation button')){
  const on=nav.dataset.screen===view;nav.setAttribute('aria-pressed',String(on));
 }
 const builderFooter=document.querySelector('.gx-actionbar');if(builderFooter)builderFooter.hidden=view!=='build';
 const d=$('gxDownload');if(d){const ready=!$('downloadXlsx')?.disabled;d.disabled=state.working||!ready||state.verifiedSnapshot!==snapshot();}
 // Review dates remain globally visible. Do not clobber user-input in the middle of a request.
}
function setFormat(format){state.format=format;
 for(const el of document.querySelectorAll('input[name="gxFormat"]'))el.checked=el.value===format;
 $('gxResultFormat').value=format;
 chrome.storage.local.set({[OUTPUT_KEY]:format}).catch(()=>{});refreshActions();
}
function bindEvents(){
 $('gxSearch').addEventListener('input',e=>{state.search=e.target.value;renderSections();});
 $('gxSelectVisible').addEventListener('click',()=>{
  const next=normalizeSelection(state.selection,{allowEmpty:true});
  // Select all search matches in expanded sections (or all expanded sections when not searching).
  for(const block of document.querySelectorAll('.gx-section')){
   if(!block.open)continue;
   for(const box of block.querySelectorAll('input[type=checkbox]')){
    const id=box.dataset.report,field=box.dataset.field;const set=new Set(next[id]||[]);
    set.add(field);next[id]=REPORTS[id].metrics.filter(k=>set.has(k));
   }
  }
  updateSelection(next);
 });
 $('gxClear').addEventListener('click',()=>updateSelection({}));
 for(const field of ['gxFrom','gxTo'])$(field).addEventListener('change',()=>setDates($('gxFrom').value,$('gxTo').value));
 for(const b of document.querySelectorAll('.gx-presets button'))b.addEventListener('click',()=>{
  const num=b.dataset.range==='yesterday'?1:Number(b.dataset.range),r=datesForLastCompleteDays(num);setDates(r.from,r.to);
 });
 $('gxConnection').addEventListener('click',connectGrafana);
 $('gxBackGrafana').addEventListener('click',()=>state.bridge?.backGrafana());
 $('gxFetch').addEventListener('click',fetchData);
 for(const field of document.querySelectorAll('input[name="gxFormat"]'))field.addEventListener('change',e=>setFormat(e.target.value));
 $('gxResultFormat').addEventListener('change',e=>setFormat(e.target.value));
 $('gxDownload').addEventListener('click',async()=>{
  if($('gxDownload').disabled)return;
  $('gxDownload').disabled=true;
  try{await state.bridge.export(state.format);}catch(e){warn(e.message);}finally{refreshActions();}
 });
 for(const b of document.querySelectorAll('.ps-navigation button'))b.addEventListener('click',()=>{
  state.bridge?.showView(b.dataset.screen);syncNavigation();refreshActions();
 });
 for(const key of ['build','results','automation'])new MutationObserver(syncNavigation).observe($('view-'+key),{attributes:true,attributeFilter:['hidden']});
 // Legacy export readiness after fetching updates through disabled attribute.
 new MutationObserver(refreshActions).observe($('downloadXlsx'),{attributes:true,attributeFilter:['disabled']});
}
async function init(){
 const bridge=window.SmartExportBridge;
 if(!bridge?.ready||state.initialized)return;
 state.bridge=bridge;state.initialized=true;
 state.selection=normalizeSelection(bridge.getSelection(),{allowEmpty:true});
 const dates=bridge.getDates();state.source=bridge.getDashboardUrl()||'';
 bindEvents();const pref=await chrome.storage.local.get({[OUTPUT_KEY]:'xlsx',[DATE_KEY]:null});
 setFormat(pref[OUTPUT_KEY]==='csvzip'?'csvzip':'xlsx');
 const saved=pref[DATE_KEY],range=saved&&validDate(saved.from)&&validDate(saved.to)&&saved.from<=saved.to&&saved.to<istToday()&&((Date.parse(saved.to)-Date.parse(saved.from))/86400000+1)<=31?saved:(dates.from&&dates.to?dates:datesForLastCompleteDays(7));
 setDates(range.from,range.to);renderSections();bridge.showView('build');syncNavigation();setConnected(false,'Checking Grafana…');
 await testConnection();
}
if(window.SmartExportBridge?.ready)init();else{
 window.addEventListener('smart-export-ready',init,{once:true});
 window.addEventListener('smart-export-error',()=>warn('Reporting engine could not load. Reload the extension.'),{once:true});
}

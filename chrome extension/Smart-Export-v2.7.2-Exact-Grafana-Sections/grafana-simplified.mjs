/* Smart Export v2.6 — Grafana-ordered, honest metric selector.
 * No added data endpoint: this controls the existing certified report engine.
 */
import {REPORT_ORDER, ALL_REPORT_ORDER, REPORTS} from './reports.mjs';
import {DETAILS, normalizeSelection} from './metric-catalog.mjs';
import {SECTIONS} from './grafana-panel-catalog.mjs';
import {datesForLastCompleteDays, istToday, validYMD, parseDashboardUrl} from './core.mjs';
const $ = id => document.getElementById(id);
// Exact Grafana panel naming where the current certified query returns the same measure.
// Hourly and combined Platform/OS exports are explicitly labeled to avoid implying
// unsupported 1-minute or 5-minute or separate-panel queries.

// One selectable card per certified metric, no synthetic data or duplicated exports.

const VISIBLE_FIELDS=SECTIONS.flatMap(s=>s.panels.flatMap(p=>(p.fields||[p.field]).map(field=>`${p.report}:${field}`)));
if(VISIBLE_FIELDS.some(k=>{const [id,field]=k.split(':');return !REPORTS[id]?.metrics.includes(field);})||
  new Set(SECTIONS.flatMap(s=>s.panels.filter(p=>!p.composite).map(p=>`${p.report}:${p.field}`))).size!==SECTIONS.flatMap(s=>s.panels.filter(p=>!p.composite)).length){
 throw new Error('Smart Export panel map is inconsistent with certified Grafana metrics.');
}
const FRIENDLY=Object.fromEntries(SECTIONS.flatMap(s=>s.panels.filter(p=>!p.composite).map(p=>[`${p.report}:${p.field}`,p.name])));
const state={bridge:null,working:false,connected:false,source:'',selection:{},search:'',format:'xlsx',initialized:false,
 expanded:new Set(SECTIONS.map(s=>s.key)),verifiedSnapshot:null,saveQueue:Promise.resolve(),saveVersion:0};
const OUTPUT_KEY='smartExportExportFormat_v26';
const visibleSelection=raw=>{
 const clean=normalizeSelection(raw,{allowEmpty:true});
 return Object.fromEntries(Object.entries(clean).map(([id,fields])=>[id,fields.filter(field=>VISIBLE_FIELDS.includes(`${id}:${field}`))]).filter(([,fields])=>fields.length));
};
const DATE_KEY='smartExportDateRange_v26';
const snapshot=()=>JSON.stringify({from:$('gxFrom').value,to:$('gxTo').value,selection:state.selection,source:state.source});
const validDate = v => typeof v==='string'&&validYMD(v);
const count=()=>SECTIONS.reduce((n,section)=>n+section.panels.filter(p=>panelSelection(p)>0).length,0);
const reportsSelected=()=>ALL_REPORT_ORDER.filter(id=>(state.selection[id]||[]).length);
const dateDays=()=>{const a=$('gxFrom').value,b=$('gxTo').value;
 if(!validDate(a)||!validDate(b))return 0;return Math.round((Date.parse(b+'T12:00:00Z')-Date.parse(a+'T12:00:00Z'))/86400000)+1;};
function warn(message){if(state.bridge?.notify){state.bridge.notify(message,'error');return;}const node=$('gxError');node.textContent=String(message);node.hidden=false;}
function clearWarn(){$('gxError').hidden=true;$('gxError').textContent='';}
function canDownload(){
 const dates=state.bridge?.getDates();
 return !state.bridge?.isBusy()&&JSON.stringify(state.bridge?.getSelection())===JSON.stringify(state.selection)&&dates?.from===$('gxFrom').value&&dates?.to===$('gxTo').value&&!$('downloadXlsx').disabled;
}
function formatMessage(){return state.format==='xlsx'?'Excel workbook · one sheet per parameter':'Individual CSVs · ZIP file';}
function validate(){
 if(!state.initialized||!state.bridge?.ready)return 'Loading reporting engine…';
 if(!validDate($('gxFrom').value)||!validDate($('gxTo').value))return 'Select valid start and end dates.';
 if(dateDays()<1)return 'The start date must not be after the end date.';
 if(dateDays()>31)return 'Select a maximum of 31 completed calendar days per request.';
 if($('gxTo').value>=istToday())return 'Use completed calendar days only (yesterday or earlier).';
 if(!count())return 'Select at least one panel.';
 // Prevent predictably oversized minute-resolution exports before querying Grafana.
 const types=reportsSelected(),days=dateDays();
 const minCount=types.filter(id=>id.endsWith('_1m')||id==='viewership_minute').length;
 const fiveCount=types.filter(id=>id.endsWith('_5m')).length;
 if(days*(minCount*1440+fiveCount*288)>115000)
   return 'Too many minute-level records for one download. Choose fewer Time Series panels or a shorter date range.';
 if(!state.source||!state.connected)return 'Open your signed-in Grafana dashboard, then choose Connect Grafana.';
 return '';
}
function setConnected(connected,message){state.connected=connected;
 if(connected){try{const filters=parseDashboardUrl(state.source).filters;if(filters.length)message+=` · ${filters.length} active ${filters.length===1?'filter':'filters'}`;}catch{}}
 const target=$('gxConnection');target.textContent=(connected?'● ':'○ ')+message;
 target.classList.toggle('is-connected',connected);target.title=connected?'Grafana tab detected. Click to check again.':'Click to connect an open Grafana tab.';
 if($('settingsConnection'))$('settingsConnection').textContent=connected?'Grafana tab detected':'Open Grafana to connect';
 refreshActions();}
function panelFields(panel){return panel.fields||[panel.field];}
function panelSelection(panel){const current=state.selection[panel.report]||[];return panelFields(panel).filter(field=>current.includes(field)).length;}
function panelFieldsFromCheckbox(box){return (box.dataset.fields||box.dataset.field||'').split(',').filter(Boolean);}
function updateChecks(){
 document.querySelectorAll('.gx-metric input[type=checkbox]').forEach(box=>{
  const keys=panelFieldsFromCheckbox(box),chosen=keys.filter(key=>(state.selection[box.dataset.report]||[]).includes(key)).length;
  const selected=chosen===keys.length&&!!chosen;
  box.checked=selected;box.indeterminate=chosen>0&&!selected;
  box.closest('.gx-metric')?.classList.toggle('is-selected',selected);
  box.closest('.gx-metric')?.classList.toggle('is-partial',chosen>0&&!selected);
  box.disabled=state.working||!!state.bridge?.isBusy();
 });
 for(const section of SECTIONS){
  const el=document.querySelector(`[data-section-count="${section.key}"]`);
  if(el){const n=section.panels.filter(p=>panelSelection(p)===panelFields(p).length).length;
   el.textContent=n?`${n} / ${section.panels.length} selected`:`${section.panels.length} panel${section.panels.length===1?'':'s'}`;el.classList.toggle('has-choices',!!n);
   const left=el.closest('.gx-section-summary')?.querySelector('.gx-section-status');if(left){left.classList.toggle('has-selection',n>0);left.textContent=n>0?'✓':'−';}}
 }
 refreshActions();
}
function refreshActions(){
 const locked=state.working||!!state.bridge?.isBusy();
 const msg=validate();const num=count();const groups=reportsSelected().length;
 $('gxCount').textContent=`${num} Grafana panel${num===1?'':'s'} selected · ${groups} data request${groups===1?'':'s'} · ${dateDays()||'—'} day${dateDays()===1?'':'s'} (IST)`;
 $('gxFetch').disabled=!!msg||locked;
 $('gxFetch').title=msg||'Fetch the selected Grafana panels';
 const hint=$('gxValidation');if(hint){hint.textContent=locked?'Please wait for the current task to finish.':msg;hint.hidden=!hint.textContent;}
 $('gxFetch').innerHTML=state.working?'Fetching Grafana data…':'Get data <span aria-hidden="true">→</span>';
 for(const btn of ['gxSelectVisible','gxClear','settingsReconnect'])if($(btn))$(btn).disabled=locked;
 for(const input of ['gxFrom','gxTo','gxSearch','gxResultFormat'])$(input).disabled=locked;
 for(const btn of document.querySelectorAll('.gx-presets button'))btn.disabled=locked;
 // Date/configuration warnings shown only once user requests data, not at startup.
 const output=$('gxDownload');
 if(output){const ready=!$('downloadXlsx')?.disabled;
  output.disabled=locked||!ready||!canDownload();
  output.textContent=state.format==='xlsx'?'Download Excel ↓':'Download CSV files ↓';
 }
}
function fieldMatches(section,panel){const q=state.search.toLocaleLowerCase().trim();
 if(!q)return true;
 return [section.title,panel.name,panel.note,...panelFields(panel).map(k=>DETAILS[k]?.help)].some(v=>String(v||'').toLocaleLowerCase().includes(q));
}
function makePanelIcon(kind){
 const span=document.createElement('span');span.className='gx-panel-icon gx-icon-'+kind;span.setAttribute('aria-hidden','true');
 // Vector icons stay legible at small Chrome sizes and do not rely on emoji fonts.
 const paths={
  users:['M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2','M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8','M22 21v-2a4 4 0 0 0-3-3.87','M16 3.13a4 4 0 0 1 0 7.75'],
  session:['M6 3h12a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2','M8 8h8','M8 12h8','M8 16h5'],
  eye:['M2 12s3.8-6.5 10-6.5 10 6.5 10 6.5-3.8 6.5-10 6.5S2 12 2 12','M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6'],
  clock:['M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20','M12 6v6l4 2'],
  trend:['M3 18l6-6 4 3 8-9','M16 6h5v5'],
  channel:['M3 5h18v14H3z','M7 19v2','M17 19v2','M7 10h10'],
  stream:['M4 7h16','M7 12h10','M4 17h16'],
  map:['M20 10c0 5-8 12-8 12S4 15 4 10a8 8 0 1 1 16 0','M12 7a3 3 0 1 0 0 6 3 3 0 0 0 0-6'],
  device:['M3 4h18v13H3z','M8 21h8','M12 17v4']
 };
 const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('width','19');svg.setAttribute('height','19');svg.setAttribute('fill','none');svg.setAttribute('stroke','currentColor');svg.setAttribute('stroke-width','1.65');svg.setAttribute('stroke-linecap','round');svg.setAttribute('stroke-linejoin','round');
 for(const d of paths[kind]||paths.session){const p=document.createElementNS('http://www.w3.org/2000/svg','path');p.setAttribute('d',d);svg.append(p);}
 span.append(svg);return span;
}
function renderSections(){
 const container=$('gxSections');const saved=new Map([...container.querySelectorAll('details')].map(x=>[x.dataset.section,x.open]));
 const host=document.createDocumentFragment();let shown=0;
 for(const [n,section] of SECTIONS.entries()){
  const metrics=section.panels.filter(p=>fieldMatches(section,p));
  if(!metrics.length)continue;shown+=metrics.length;
  const block=document.createElement('details');block.className='gx-section gx-layout-'+section.style;block.dataset.section=section.key;
  block.open=state.search.trim()?true:(saved.has(section.key)?saved.get(section.key):state.expanded.has(section.key));
  const sum=document.createElement('summary');sum.className='gx-section-summary';
  const left=document.createElement('span');left.className='gx-section-status';left.setAttribute('aria-hidden','true');left.textContent='−';
  const titleBox=document.createElement('span');titleBox.className='gx-section-copy';
  const title=document.createElement('strong');title.textContent=section.title;titleBox.append(title);
  if(section.description){const desc=document.createElement('small');desc.textContent=section.description;titleBox.append(desc);}
  const selected=document.createElement('span');selected.className='gx-section-count';selected.dataset.sectionCount=section.key;
  const number=section.panels.filter(p=>panelSelection(p)===panelFields(p).length).length;
  selected.textContent=number?`${number} / ${section.panels.length} selected`:`${section.panels.length} panel${section.panels.length===1?'':'s'}`;
  left.classList.toggle('has-selection',number>0);left.textContent=number>0?'✓':'−';
  const chevron=document.createElement('span');chevron.className='gx-chevron';chevron.setAttribute('aria-hidden','true');
  sum.append(left,titleBox,selected,chevron);
  const grid=document.createElement('div');grid.className='gx-metric-grid';
  for(const panel of metrics){
   const label=document.createElement('label');label.className='gx-metric'+(panel.composite?' gx-metric-table':'')+(panel.layout?' gx-'+panel.layout:'');label.dataset.report=panel.report;if(panel.field)label.dataset.field=panel.field;
   if(panel.panel)label.dataset.grafanaPanelId=String(panel.panel);
   const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.dataset.report=panel.report;
   if(panel.composite)checkbox.dataset.fields=panel.fields.join(',');else checkbox.dataset.field=panel.field;
   const chosen=panelSelection(panel);checkbox.checked=chosen===panelFields(panel).length;checkbox.indeterminate=chosen>0&&!checkbox.checked;checkbox.disabled=state.working||!!state.bridge?.isBusy();
   checkbox.setAttribute('aria-label',`Export ${panel.name}`);
   const icon=makePanelIcon(panel.icon);
   const copy=document.createElement('span');copy.className='gx-metric-copy';
   const metricTitle=document.createElement('strong');metricTitle.textContent=panel.name;
   const help=document.createElement('small');help.textContent=panel.note||DETAILS[panel.field]?.help||'';
   copy.append(metricTitle,help);
   if(panel.composite){const pairs=document.createElement('span');pairs.className='gx-table-fields';
    for(const [field,title] of panel.compositeColumns||[]){const col=document.createElement('span');col.className='gx-table-column';col.textContent=title;col.dataset.sourceColumn=field;pairs.append(col);}
    copy.append(pairs);}
   label.append(checkbox,icon,copy);
   label.classList.toggle('is-selected',checkbox.checked);label.classList.toggle('is-partial',checkbox.indeterminate);
   label.title=`${panel.name} — ${DETAILS[panel.field]?.help||panel.note||''}`;
   checkbox.addEventListener('change',()=>toggleMetric(panel.report,panelFields(panel),checkbox.checked));grid.append(label);
  }
  block.append(sum,grid);block.addEventListener('toggle',()=>{
   if(!state.search.trim()){if(block.open)state.expanded.add(section.key);else state.expanded.delete(section.key);}
  });host.append(block);
 }
 container.replaceChildren(host);
 if(!shown){const p=document.createElement('p');p.className='gx-no-match';p.textContent='No matching panels. Try “sessions”, “per minute”, “playtime”, or “device”.';container.append(p);}
 refreshActions();
}
async function updateSelection(next){
 if(!state.bridge?.ready||state.working||state.bridge.isBusy())return;
 const old=state.selection;
 let clean;
 try{clean=visibleSelection(next);}catch(e){warn(e.message);return;}
 state.selection=clean;state.verifiedSnapshot=null;updateChecks();clearWarn();
 // Serialize changes: fast consecutive checkbox clicks must not save out of order.
 const version=++state.saveVersion;
 const latest=state.saveQueue.catch(()=>{}).then(()=>state.bridge.setSelection(clean));
 state.saveQueue=latest;
 try{if(await latest===false)throw new Error('Your selection could not be saved. Try again.');}
 catch(e){if(version===state.saveVersion){state.selection=old;updateChecks();warn(`Selection could not be saved: ${e.message}`);}}
}
async function toggleMetric(id,fields,on){
 const next=normalizeSelection(state.selection,{allowEmpty:true});const set=new Set(next[id]||[]);
 for(const field of fields){if(on)set.add(field);else set.delete(field);}
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
  await state.saveQueue;
  // Grafana can change filters after the workspace opened. Re-select the live
  // tab before saving/fetching so its data goes into the correct filter dataset.
  state.source=await state.bridge.useGrafana();state.verifiedSnapshot=null;
  setConnected(true,'Grafana connected');
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
 const d=$('gxDownload');if(d)d.disabled=state.working||!canDownload();
 // Review dates remain globally visible. Do not clobber user-input in the middle of a request.
}
function setFormat(format){state.format=format;
 $('gxResultFormat').value=format;
 chrome.storage.local.set({[OUTPUT_KEY]:format}).catch(()=>{});refreshActions();
}
function bindEvents(){
 $('gxSearch').addEventListener('input',e=>{state.search=e.target.value;renderSections();});
 $('gxSelectVisible').addEventListener('click',()=>{
  const next=normalizeSelection(state.selection,{allowEmpty:true});
  // Select visible panels in currently expanded sections; never select hidden search matches.
  for(const block of document.querySelectorAll('.gx-section')){
   if(!block.open)continue;
   for(const box of block.querySelectorAll('input[type=checkbox]')){
    const id=box.dataset.report,fields=panelFieldsFromCheckbox(box);const set=new Set(next[id]||[]);
    for(const field of fields)set.add(field);next[id]=REPORTS[id].metrics.filter(k=>set.has(k));
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
 $('settingsReconnect')?.addEventListener('click',connectGrafana);
 $('gxBackGrafana').addEventListener('click',()=>state.bridge?.backGrafana());
 $('gxFetch').addEventListener('click',fetchData);
 $('gxResultFormat').addEventListener('change',e=>setFormat(e.target.value));
 $('gxDownload').addEventListener('click',async()=>{
  if($('gxDownload').disabled)return;
  $('gxDownload').disabled=true;
  try{await state.bridge.export(state.format);}catch(e){warn(e.message);}finally{refreshActions();}
 });
 for(const b of document.querySelectorAll('.ps-navigation button'))b.addEventListener('click',()=>{
  state.bridge?.showView(b.dataset.screen);syncNavigation();refreshActions();
 });
 const nav=[...document.querySelectorAll('.ps-navigation button')];
 for(const button of nav){button.setAttribute('aria-controls','view-'+button.dataset.screen);button.addEventListener('keydown',event=>{
  if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
  event.preventDefault();let index=nav.indexOf(button);
  index=event.key==='Home'?0:event.key==='End'?nav.length-1:(index+(event.key==='ArrowRight'?1:-1)+nav.length)%nav.length;
  nav[index].click();nav[index].focus();
 });}
 for(const key of ['build','results','automation'])new MutationObserver(syncNavigation).observe($('view-'+key),{attributes:true,attributeFilter:['hidden']});
 // Legacy export readiness after fetching updates through disabled attribute.
 new MutationObserver(refreshActions).observe($('downloadXlsx'),{attributes:true,attributeFilter:['disabled']});
 window.addEventListener('smart-export-busy',updateChecks);
 window.addEventListener('smart-export-selection-changed',async event=>{
  const clean=visibleSelection(event.detail.selection);
  if(JSON.stringify(clean)===JSON.stringify(state.selection))return;
  state.selection=clean;state.verifiedSnapshot=null;renderSections();syncNavigation();
  if(JSON.stringify(clean)!==JSON.stringify(event.detail.selection)){
   try{await state.bridge.setSelection(clean);}catch(e){warn(e.message);}
  }
 });
}
async function init(){
 const bridge=window.SmartExportBridge;
 if(!bridge?.ready||state.initialized)return;
 state.bridge=bridge;state.initialized=true;
 state.selection=visibleSelection(bridge.getSelection());
 const dates=bridge.getDates();state.source=bridge.getDashboardUrl()||'';
 bindEvents();const pref=await chrome.storage.local.get({[OUTPUT_KEY]:'xlsx',[DATE_KEY]:null});
 if(JSON.stringify(state.selection)!==JSON.stringify(bridge.getSelection()))await bridge.setSelection(state.selection);
 setFormat(pref[OUTPUT_KEY]==='csvzip'?'csvzip':'xlsx');
 const saved=pref[DATE_KEY],range=saved&&validDate(saved.from)&&validDate(saved.to)&&saved.from<=saved.to&&saved.to<istToday()&&((Date.parse(saved.to)-Date.parse(saved.from))/86400000+1)<=31?saved:(dates.from&&dates.to?dates:datesForLastCompleteDays(7));
 setDates(range.from,range.to);renderSections();bridge.showView('build');syncNavigation();setConnected(false,'Checking Grafana…');
 await testConnection();
}
const start=()=>init().catch(e=>{state.initialized=false;warn(`Workspace could not load: ${e.message}. Reload the extension and reopen this tab.`);});
if(window.SmartExportBridge?.ready)start();else{
 window.addEventListener('smart-export-ready',start,{once:true});
 window.addEventListener('smart-export-error',()=>warn('Reporting engine could not load. Reload the extension.'),{once:true});
}

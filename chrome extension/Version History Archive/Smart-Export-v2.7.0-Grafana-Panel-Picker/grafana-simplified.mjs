/* Smart Export v2.6 — Grafana-ordered, honest metric selector.
 * No added data endpoint: this controls the existing certified report engine.
 */
import {REPORT_ORDER, REPORTS} from './reports.mjs';
import {DETAILS, normalizeSelection} from './metric-catalog.mjs';
import {datesForLastCompleteDays, istToday, validYMD} from './core.mjs';
const $ = id => document.getElementById(id);
// Exact Grafana panel naming where the current certified query returns the same measure.
// Hourly and combined Platform/OS exports are explicitly labeled to avoid implying
// unsupported 1-minute or 5-minute or separate-panel queries.
const SECTIONS = [
 {key:'session',title:'Session and Users Stats',style:'stats',panels:[
  {report:'kpis',field:'unique_devices',name:'Total Users ( Based on Device ID - APP DATA)',note:'Distinct device IDs · daily',panel:2,icon:'users'},
  {report:'kpis',field:'session_ids',name:'Total Sessions (Based on Session ID in query String - APP DATA)',note:'Distinct session IDs · daily',panel:1,icon:'session'},
  {report:'kpis',field:'unique_ips',name:'Total Users (Based on Uniq IP)',note:'Distinct client IPs · daily',panel:8,icon:'users'},
  {report:'kpis',field:'ip_ua_sessions',name:'Total Sessions (Based on Uniq IP & UA)',note:'Unique IP + user-agent pairs · daily',panel:12,icon:'session'},
  {report:'kpis',field:'manifest_views',name:'Total Views (Total Master Manifest Requests)',note:'Matching master-manifest requests',panel:5,icon:'eye'},
 ]},
 {key:'series',title:'Time Series',style:'series',description:'Hourly export data, not the per-minute or 5-minute Grafana charts',panels:[
  {report:'traffic',field:'unique_ips',name:'Total Users (Based on Uniq IP) — Hourly',note:'Hourly unique IPs',icon:'trend'},
  {report:'traffic',field:'session_ids',name:'Total Sessions (Based on Session ID) — Hourly',note:'Hourly distinct sessions',icon:'trend'},
  {report:'traffic',field:'manifest_views',name:'Total Views (Total Master Manifest Requests) — Hourly',note:'Hourly manifest requests',icon:'trend'},
  {report:'traffic',field:'playtime_minutes',name:'Viewership minutes — Hourly',note:'Hourly estimated playtime',icon:'trend'},
  {report:'traffic',field:'bandwidth_bytes',name:'Total Bandwidth (Video) — Hourly',note:'Hourly transfer bytes',icon:'trend'},
 ]},
 {key:'viewership',title:'Viewership Trend',style:'viewership',panels:[
  {report:'kpis',field:'playtime_minutes',name:'Viewership minutes',note:'Daily estimate from 6-second segments',panel:17,icon:'clock'},
  {report:'kpis',field:'bandwidth_bytes',name:'Total Bandwidth (Video)',note:'Daily video bytes',panel:15,icon:'stream'},
  {report:'channel',field:'playtime_minutes',name:'Playtime by Channel',note:'Date + channel · minutes',panel:34,icon:'channel'},
  {report:'channel',field:'unique_ips',name:'Total Users (Based on Uniq IP) · Channel',note:'Date + channel · unique client IPs',panel:68,icon:'users'},
 ]},
 {key:'content',title:'Popular Content',style:'content',panels:[
  {report:'content',field:'unique_ips',name:'Users (Based on Uniq IP)',note:'Date + content title',panel:27,icon:'users'},
  {report:'content',field:'unique_devices',name:'Users ( Based on Device ID - APP DATA)',note:'Date + content title',panel:27,icon:'users'},
  {report:'content',field:'session_ids',name:'Total Sessions (Based on Session ID in query String - APP DATA)',note:'Date + content title',panel:27,icon:'session'},
  {report:'content',field:'manifest_views',name:'views',note:'Matching manifest requests by title',panel:27,icon:'eye'},
 ]},
 {key:'playtime',title:'Playtime',style:'playtime',panels:[
  {report:'geo',field:'playtime_minutes',name:'Playtime by GEO',note:'Country · state · city · minutes',panel:20,icon:'map'},
  {report:'devices',field:'unique_devices',name:'Total Device ID by Platform',note:'Includes platform and OS in export',panel:58,icon:'device'},
 ]},
 {key:'ip',title:'Playtime - IP',style:'playtime-ip',panels:[
  {report:'devices',field:'unique_ips',name:'IP by Platform(sessions)',note:'Distinct IPs · grouped by platform and OS',panel:33,icon:'device'},
 ]},
];
// One selectable card per certified metric, no synthetic data or duplicated exports.
const VISIBLE_FIELDS=SECTIONS.flatMap(s=>s.panels.map(p=>`${p.report}:${p.field}`));
if(new Set(VISIBLE_FIELDS).size!==VISIBLE_FIELDS.length||
  VISIBLE_FIELDS.some(k=>{const [id,field]=k.split(':');return !REPORTS[id]?.metrics.includes(field);})){
 throw new Error('Smart Export panel map is inconsistent with certified Grafana metrics.');
}
const FRIENDLY=Object.fromEntries(SECTIONS.flatMap(s=>s.panels.map(p=>[`${p.report}:${p.field}`,p.name])));
const state={bridge:null,working:false,connected:false,source:'',selection:{},search:'',format:'xlsx',initialized:false,
 expanded:new Set(['session','series','viewership','content','playtime','ip']),verifiedSnapshot:null};
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
function formatMessage(){return state.format==='xlsx'?'Excel workbook · one sheet per parameter':'Individual CSVs · ZIP file';}
function validate(){
 if(!state.initialized||!state.bridge?.ready)return 'Loading reporting engine…';
 if(!validDate($('gxFrom').value)||!validDate($('gxTo').value))return 'Select valid start and end dates.';
 if(dateDays()<1)return 'The start date must not be after the end date.';
 if(dateDays()>31)return 'Select a maximum of 31 completed calendar days per request.';
 if($('gxTo').value>=istToday())return 'Use completed calendar days only (yesterday or earlier).';
 if(!count())return 'Select at least one panel.';
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
 for(const section of SECTIONS){
  const el=document.querySelector(`[data-section-count="${section.key}"]`);
  if(el){const n=section.panels.filter(p=>(state.selection[p.report]||[]).includes(p.field)).length;
   el.textContent=n?`${n} / ${section.panels.length} selected`:`${section.panels.length} panel${section.panels.length===1?'':'s'}`;el.classList.toggle('has-choices',!!n);
   const left=el.closest('.gx-section-summary')?.querySelector('.gx-section-status');if(left){left.classList.toggle('has-selection',n>0);left.textContent=n>0?'✓':'−';}}
 }
 refreshActions();
}
function refreshActions(){
 const msg=validate();const num=count();const groups=reportsSelected().length;
 $('gxCount').textContent=`${num} panel${num===1?'':'s'} selected · ${groups} dataset${groups===1?'':'s'} · ${dateDays()||'—'} day${dateDays()===1?'':'s'} (IST)`;
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
function fieldMatches(section,panel){const q=state.search.toLocaleLowerCase().trim();
 if(!q)return true;
 return [section.title,panel.name,panel.note,DETAILS[panel.field]?.help].some(v=>String(v||'').toLocaleLowerCase().includes(q));
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
  const number=section.panels.filter(p=>(state.selection[p.report]||[]).includes(p.field)).length;
  selected.textContent=number?`${number} / ${section.panels.length} selected`:`${section.panels.length} panel${section.panels.length===1?'':'s'}`;
  left.classList.toggle('has-selection',number>0);left.textContent=number>0?'✓':'−';
  const chevron=document.createElement('span');chevron.className='gx-chevron';chevron.setAttribute('aria-hidden','true');
  sum.append(left,titleBox,selected,chevron);
  const grid=document.createElement('div');grid.className='gx-metric-grid';
  for(const panel of metrics){
   const label=document.createElement('label');label.className='gx-metric';label.dataset.report=panel.report;label.dataset.field=panel.field;
   if(panel.panel)label.dataset.grafanaPanelId=String(panel.panel);
   const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.dataset.report=panel.report;checkbox.dataset.field=panel.field;
   checkbox.checked=(state.selection[panel.report]||[]).includes(panel.field);checkbox.disabled=state.working;
   checkbox.setAttribute('aria-label',`Export ${panel.name}`);
   const icon=makePanelIcon(panel.icon);
   const copy=document.createElement('span');copy.className='gx-metric-copy';
   const metricTitle=document.createElement('strong');metricTitle.textContent=panel.name;
   const help=document.createElement('small');help.textContent=panel.note||DETAILS[panel.field]?.help||'';
   copy.append(metricTitle,help);
   label.append(checkbox,icon,copy);
   label.classList.toggle('is-selected',checkbox.checked);
   label.title=`${panel.name} — ${DETAILS[panel.field]?.help||panel.note||''}`;
   checkbox.addEventListener('change',()=>toggleMetric(panel.report,panel.field,checkbox.checked));grid.append(label);
  }
  block.append(sum,grid);block.addEventListener('toggle',()=>{
   if(!state.search.trim()){if(block.open)state.expanded.add(section.key);else state.expanded.delete(section.key);}
  });host.append(block);
 }
 container.replaceChildren(host);
 if(!shown){const p=document.createElement('p');p.className='gx-no-match';p.textContent='No matching panels. Try “users”, “playtime”, “content”, or “device”.';container.append(p);}
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
  // Select visible panels in currently expanded sections; never select hidden search matches.
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

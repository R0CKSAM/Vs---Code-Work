/* Smart Export v2.3.0 — production UI with isolated views and a flat metric picker.
   The Grafana background engine and export writers are unchanged. */
import {DEFAULT_CONFIG,parseDashboardUrl,datesForLastCompleteDays,istToday} from './core.mjs';
import {REPORT_ORDER,ALL_REPORT_ORDER,REPORTS} from './reports.mjs';
import {GROUPS,DETAILS,FIELD_LABELS,PRESETS,DEFAULT_SELECTION,normalizeSelection,selectedColumns,selectionCounts,selectionReports} from './metric-catalog.mjs';
import {allReportRows} from './report-db.mjs';
import {buildPickedWorkbook} from './multi-xlsx.mjs';
import {rowsForExport,selectedCsv} from './picked-export.mjs';
import {buildCsvZip} from './csv-zip.mjs';

const $=id=>document.getElementById(id);
const STORE='smartExportSmartPicker_v21',VIEWS='smartExportSavedViews_v21';
let selection=normalizeSelection(DEFAULT_SELECTION),working=false,config={...DEFAULT_CONFIG};
let summaries={},coverage={},allData={},savedViews={},lastDataKey='',latestActivity=null,filter={field:'',text:''};
let activePreset='overview';
// Keep accordions stable across checkbox changes, search, and persisted view selections.
let activeCategory = 'kpis';
const UI_VIEW='smartExportActiveView_v22';
let currentView='build';
const send=(type,args={})=>new Promise((resolve,reject)=>chrome.runtime.sendMessage({type,...args},res=>{
 if(chrome.runtime.lastError)return reject(new Error(chrome.runtime.lastError.message));
 if(!res)return reject(new Error('Smart Export is not responding. Reload the extension in Chrome.'));
 if(!res.ok)return reject(new Error(res.error||'Unknown Grafana export error.'));
 resolve(res.data);
}));
const show=(value,kind='info')=>{
 const el=$('feedback');el.textContent=String(value);
 el.className='feedback '+(kind==='warning'?'warn':kind==='error'?'error':kind==='success'?'success':'');
 el.title=String(value);const wrap=el.closest('.feedback-wrap');if(wrap)wrap.dataset.kind=kind;
 const helper=$('feedbackHelp'),dismiss=$('feedbackDismiss');if(helper)helper.hidden=kind!=='error';if(dismiss)dismiss.hidden=!['success','error','warning'].includes(kind);
};
function switchView(view,{remember=true}={}){
 if(!['build','results','automation'].includes(view))view='build';
 currentView=view;
 for(const key of ['build','results','automation']){
  const panel=$('view-'+key),tab=$('tab'+(key==='build'?'Build':key==='results'?'Results':'Automation'));
  const active=key===view; panel.hidden=!active;tab.classList.toggle('active',active);
  tab.setAttribute('aria-selected',String(active));tab.tabIndex=active?0:-1;
 }
 if(remember){chrome.storage.local.set({[UI_VIEW]:view}).catch(()=>{});}
 if(document.body.classList.contains('workspace-mode')){const viewEl=$('view-'+view);if(viewEl)viewEl.scrollTop=0;}
}
function bindNavigation(){
 for(const tab of document.querySelectorAll('.page-tab')){
  tab.addEventListener('click',()=>switchView(tab.dataset.view));
  tab.addEventListener('keydown',(event)=>{
   if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
   event.preventDefault();const order=['build','results','automation'];let i=order.indexOf(tab.dataset.view);
   i=event.key==='Home'?0:event.key==='End'?2:(i+(event.key==='ArrowRight'?1:-1)+order.length)%order.length;
   switchView(order[i]);$('tab'+(order[i]==='build'?'Build':order[i]==='results'?'Results':'Automation')).focus();
  });
 }
}

const dateStamp=ts=>{if(!ts)return 'Never';try{return new Date(ts).toLocaleString('en-IN',{dateStyle:'medium',timeStyle:'short',timeZone:'Asia/Kolkata'});}catch{return '—';}};
const presetDates=n=>{const r=datesForLastCompleteDays(n);$('dateFrom').value=r.from;$('dateTo').value=r.to;for(const size of [7,30]){const b=$(size===7?'last7':'last30');b.classList.toggle('is-active',size===n);b.setAttribute('aria-pressed',String(size===n));}};
const identical=(a,b)=>JSON.stringify(normalizeSelection(a,{allowEmpty:true}))===JSON.stringify(normalizeSelection(b,{allowEmpty:true}));
const ids=()=>selectionReports(selection);
const prettyCount=n=>Number(n||0).toLocaleString('en-IN');
const download=(blob,name)=>{const u=URL.createObjectURL(blob),a=document.createElement('a');a.href=u;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),45000);};
function busy(isBusy){
 working=!!isBusy;
 // A fetch must use one immutable selection/date/source. Prevent mid-request edits
 // that previously made the visible selection disagree with fetched categories.
 for(const id of ['useCurrent','syncNow','autoDaily','last7','last30','savePreset','loadPreset','deletePreset','scanPanels','clearData','classic',
   'metricSearch','clearSearch','dashboardUrl','dateFrom','dateTo','presetName','savedPresets',
   'filterField','filterText']) $(id).disabled=working;
 for(const el of document.querySelectorAll('#quickPicks button, #categoryTabs button, #metricCatalog input, #selectedChips button')) el.disabled=working;
 document.querySelector('#metricCatalog').classList.toggle('is-busy',working);
 $('syncLabel').textContent=working?'Fetching your numbers…':'Fetch selected data';
 $('dockFetch').innerHTML=working?'Fetching…':'Fetch data <span aria-hidden="true">→</span>'; 
 updateButtons();
}
function updateButtons(){
 const types=ids(),sameSource=$('dashboardUrl').value.trim()===(config.dashboardUrl||'').trim();
 const ready=types.length&&sameSource&&types.every(id=>Number(summaries[id]?.rows)>0);
 $('downloadXlsx').disabled=working||!ready;
 $('downloadCsv').disabled=working||!ready||types.length!==1;
 $('downloadCsv').title=types.length!==1?'CSV supports one report category. Excel contains a tab for each selected category.':'';
 $('syncNow').disabled=working||!types.length;
 $('dockFetch').disabled=working||!types.length;
 $('dockExcel').disabled=working||!ready;
}
function renderQuickPicks(){
 const host=$('quickPicks');
 // Create once. Replacing an active button after click used to discard keyboard
 // focus and interrupt repeated keyboard navigation through presets.
 for(const [key,p] of Object.entries(PRESETS)){
  let b=host.querySelector(`button[data-preset="${key}"]`);
  if(!b){
   b=document.createElement('button');b.type='button';b.className='quick-btn';b.dataset.preset=key;
   const label=document.createElement('strong');label.textContent=p.title;
   const sub=document.createElement('small');sub.textContent=p.hint;
   b.append(label,sub);b.addEventListener('click',()=>setSelection(p.selection,{announce:true}));
   host.append(b);
  }
  const active=identical(selection,p.selection);
  b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));b.disabled=working;
  if(active)activePreset=key;
 }
}
function renderCategoryTabs(){
 const host=$('categoryTabs'),searching=!!$('metricSearch').value.trim();
 for(const id of REPORT_ORDER){
  const group=GROUPS[id],count=(selection[id]||[]).length;
  let b=host.querySelector(`button[data-category="${id}"]`);
  if(!b){
   b=document.createElement('button');b.type='button';b.className='category-btn';b.dataset.category=id;
   b.addEventListener('click',()=>{if(working)return;$('metricSearch').value='';activeCategory=id;renderCategoryTabs();renderCatalog();});
   const title=document.createElement('span');title.className='cat-title';title.textContent=group.title;
   const countSpan=document.createElement('span');countSpan.className='cat-count';b.append(title,countSpan);host.append(b);
  }
  b.querySelector('.cat-count').textContent=String(count);
  b.querySelector('.cat-count').hidden=!count;
  b.title=group.short;
  b.classList.toggle('active',!searching&&activeCategory===id);
  b.setAttribute('aria-pressed',String(!searching&&activeCategory===id));
  b.disabled=working;
 }
}
function renderCatalog(){
 const host=$('metricCatalog'),needle=$('metricSearch').value.trim().toLocaleLowerCase();
 const previousScroll=host.scrollTop;
 host.replaceChildren();let count=0;
 const visibleIds=needle?REPORT_ORDER:[activeCategory];
 for(const id of visibleIds){
  const group=GROUPS[id];
  const matches=REPORTS[id].metrics.filter(field=>!needle||
    [group.title,group.section,group.short,field,DETAILS[field]?.label,DETAILS[field]?.help]
      .some(text=>String(text||'').toLocaleLowerCase().includes(needle)));
  if(!matches.length)continue;
  if(needle){const heading=document.createElement('div');heading.className='metric-group-heading';heading.textContent=group.title;host.append(heading);}
  for(const field of matches){
   count++;
   const label=document.createElement('label');label.className='metric-item';
   const checked=(selection[id]||[]).includes(field);label.classList.toggle('checked',checked);
   const input=document.createElement('input');input.type='checkbox';input.checked=checked;input.dataset.report=id;input.dataset.metric=field;
   input.setAttribute('aria-label',`${DETAILS[field]?.label||field}, ${group.title}`);input.disabled=working;
   input.addEventListener('change',()=>toggleMetric(id,field,input.checked));
   const copy=document.createElement('span');copy.className='metric-copy';
   const title=document.createElement('strong');title.textContent=DETAILS[field]?.label||field;
   const help=document.createElement('small');help.textContent=DETAILS[field]?.help||'';
   copy.append(title,help);label.append(input,copy);host.append(label);
  }
 }
 if(!count){const p=document.createElement('p');p.className='nothing';p.textContent='No matching metrics. Try users, channel, session, GEO, or playtime.';host.append(p);}
 $('catalogTitle').textContent=needle?`Results for “${$('metricSearch').value.trim().slice(0,45)}”`:GROUPS[activeCategory].title;
 $('catalogCount').textContent=`${count} metric${count===1?'':'s'}`;
 host.scrollTop=needle?0:Math.min(previousScroll,Math.max(0,host.scrollHeight-host.clientHeight));
 renderCategoryTabs();
}
function renderSelected(){
 const choice=normalizeSelection(selection,{allowEmpty:true}),stats=selectionCounts(choice),host=$('selectedChips');host.replaceChildren();
 $('selectedCount').textContent=`${stats.metrics} metric${stats.metrics===1?'':'s'}`;
 $('sourceCount').textContent=`${stats.reports} group${stats.reports===1?'':'s'}`;
 $('sheetHint').textContent=stats.reports===0?'Choose a metric':stats.reports===1?'One Excel report tab':`${stats.reports} Excel tabs, no unsafe joins`;
 for(const id of ALL_REPORT_ORDER)for(const field of choice[id]||[]){
  const item=document.createElement('div');item.className='selected-chip';
  const text=document.createElement('span');text.textContent=`${GROUPS[id].title}: ${DETAILS[field]?.label||field}`;text.title=text.textContent;
  const remove=document.createElement('button');remove.type='button';remove.disabled=working;remove.textContent='×';remove.setAttribute('aria-label',`Remove ${text.textContent}`);remove.addEventListener('click',()=>toggleMetric(id,field,false));
  item.append(text,remove);host.append(item);
 }
 if(!stats.metrics){const empty=document.createElement('span');empty.className='subtext';empty.textContent='Your selection will appear here.';host.append(empty);}
}
function draw(){renderQuickPicks();renderCategoryTabs();renderCatalog();renderSelected();renderFilter();updateStats();renderPreview();updateButtons();}
// Do not destroy focused checkbox DOM on each selection: previously this reset the
// scroll position, closed a dropdown under the cursor, and broke keyboard focus.
function updateCatalogChecks(){
 for(const box of document.querySelectorAll('#metricCatalog input[type=checkbox]')){
  const checked=(selection[box.dataset.report]||[]).includes(box.dataset.metric);
  box.checked=checked;box.closest('.metric-item').classList.toggle('checked',checked);
 }
 renderCategoryTabs();
}
async function saveChoice(){await chrome.storage.local.set({[STORE]:selection});}
async function setSelection(input,{announce=false,fromCheckbox=false}={}){
 if(working)return;
 selection=normalizeSelection(input,{allowEmpty:true});
 if(fromCheckbox){
  // Preserve accordion position, checked checkbox focus, and native dropdown state.
  updateCatalogChecks();renderQuickPicks();renderSelected();renderFilter();updateStats();renderPreview();updateButtons();
 }else{
  activeCategory=ids()[0]||'kpis';draw();
 }
 try{await saveChoice();}catch(e){show(`Could not save metric selection: ${e.message}`,'error');return;}
 if(config.enabled&&config.autoReport==='picked'&&!sameReports(ids(),config.autoReports||[])){
  try{const old=config.autoReports?.length?config.autoReports:ids();await send('ENABLE_PICKED',{enabled:false,reports:old});config.enabled=false;$('autoDaily').checked=false;updateStats();show('Your scheduled categories changed. Daily updates have been paused until you review the new selection.','warning');}
  catch(e){show('Could not pause the old scheduled selection: '+e.message,'error');}
 }
 if(announce)show(`${selectionCounts(selection).metrics} metrics selected. Pick dates and fetch the data.`, 'success');
}
const sameReports=(a,b)=>JSON.stringify(ALL_REPORT_ORDER.filter(id=>a.includes(id)))===JSON.stringify(ALL_REPORT_ORDER.filter(id=>b.includes(id)));
function toggleMetric(id,field,checked){
 const choice=normalizeSelection(selection,{allowEmpty:true}),set=new Set(choice[id]||[]);
 if(checked)set.add(field);else set.delete(field);
 if(set.size)choice[id]=REPORTS[id].metrics.filter(x=>set.has(x));else delete choice[id];
 setSelection(choice,{fromCheckbox:true});
}
function renderFilter(){
 const host=$('exportFilterBox'),selected=ids();
 if(selected.length!==1){host.hidden=true;host.dataset.report='';filter={field:'',text:''};$('filterText').value='';return;}
 const reportId=selected[0],report=REPORTS[reportId],dims=report.dimension.filter(x=>x!=='date');
 host.hidden=!dims.length;
 const field=$('filterField');
 // A filter for Channels should not silently carry over to Locations or Content.
 if(host.dataset.report!==reportId){filter={field:'',text:''};$('filterText').value='';host.dataset.report=reportId;}
 const oldOptions=[...field.options].map(x=>x.value);
 if(JSON.stringify(oldOptions)!==JSON.stringify(dims)){
  field.replaceChildren();
  for(const key of dims){const opt=document.createElement('option');opt.value=key;opt.textContent=FIELD_LABELS[key]||key;field.append(opt);}
 }
 if(dims.includes(filter.field))field.value=filter.field;else filter.field=field.value;
}
function filterConfig(){return ids().length===1 && !$('exportFilterBox').hidden && $('filterText').value.trim()?{
 field:$('filterField').value,text:$('filterText').value.trim()
 }:null;}
function dataSelected(){return rowsForExport(allData,selection,filterConfig());}
function renderPreview(){
 const types=ids(),table=$('previewTable'),thead=table.querySelector('thead'),tbody=table.querySelector('tbody');
 thead.replaceChildren();tbody.replaceChildren();
 const eligible=types.find(id=>(allData[id]||[]).length);
 if(!eligible){$('previewScroll').hidden=false;table.hidden=true;$('previewEmpty').hidden=false;$('previewName').textContent='Preview of selected fields';$('previewMeta').textContent='Not fetched';$('previewEmpty').textContent='Fetch selected data to preview its columns and example rows.';return;}
 let rows=[];try{rows=dataSelected()[eligible]||[];}catch(e){show(e.message,'error');}
 const cols=selectedColumns(eligible,selection);
 $('previewName').textContent=GROUPS[eligible].title;
 $('previewMeta').textContent=`${prettyCount(rows.length)} matching rows`;
 const tr=document.createElement('tr');for(const [,label] of cols){const th=document.createElement('th');th.textContent=label;tr.append(th);}thead.append(tr);
 for(const r of rows.slice(0,4)){const tr=document.createElement('tr');for(const [key] of cols){const td=document.createElement('td');const val=r[key];td.textContent=typeof val==='number'?val.toLocaleString('en-IN',{maximumFractionDigits:2}):String(val??'');td.title=String(val??'');tr.append(td);}tbody.append(tr);}
 table.hidden=false;$('previewEmpty').hidden=rows.length>0;
 if(!rows.length)$('previewEmpty').textContent='No rows match this optional export filter. Clear the filter to include more data.';
}
function updateStats(){
 const reports=ids(),summariesChosen=reports.map(id=>summaries[id]||{}),total=summariesChosen.reduce((n,a)=>n+(a.rows||0),0);
 const dates=new Set();for(const id of reports)for(const r of allData[id]||[])dates.add(r.date);
 $('rowCount').textContent=prettyCount(total);$('dayCount').textContent=prettyCount(dates.size);
 $('variantCount').textContent=prettyCount(reports.filter(id=>summaries[id]?.rows).length);
 const vals=summariesChosen.filter(x=>x.rows);
 $('rangeDetails').textContent=vals.length?`Saved dates: ${vals.map(x=>x.from).sort()[0]} to ${vals.map(x=>x.to).sort().at(-1)}. All six certified datasets remain available when requested.`:'No saved rows for your chosen categories yet.';
 const ready=reports.length&&$('dashboardUrl').value.trim()===(config.dashboardUrl||'').trim()&&reports.every(id=>summaries[id]?.rows);
 const status=$('stateChip');status.textContent=working?'FETCHING':config.enabled?'DAILY ON':ready?'READY TO EXPORT':'NOT FETCHED';
 status.className='state-chip '+(working?'working':config.enabled?'':'warn');
 $('autoDaily').checked=!!config.enabled&&!!config.v2Mode&&config.autoReport==='picked'&&sameReports(reports,config.autoReports||[]);
 $('dockStatus').textContent=working?'Fetching reports…':!$('dashboardUrl').value.trim()?'Choose Grafana tab':`${selectionCounts(selection).metrics} metrics · ${prettyCount(total)} saved rows`;
 $('lastSynced').textContent=`Last successful fetch: ${dateStamp(config.lastSuccessAt)}. ${config.enabled?`Active schedule: ${config.autoReport==='picked'?'Smart Picker':config.autoReport||'legacy'} categories.`:'Daily updates are off.'}`;
}
async function loadState({showActivity=false}={}){
 try{
  const r=await send('STATE_V2');config={...DEFAULT_CONFIG,...r.config};summaries=r.summaries||{};coverage=r.coverage||{};
  if(document.activeElement!==$('dashboardUrl'))$('dashboardUrl').value=config.dashboardUrl;
  const spec=parseDashboardUrl(config.dashboardUrl);
  if(lastDataKey!==spec.datasetKey || !Object.keys(allData).length){allData=await allReportRows(spec.datasetKey);lastDataKey=spec.datasetKey;}
  else{allData=await allReportRows(spec.datasetKey);}
  updateStats();renderPreview();updateButtons();
  if(showActivity&&r.activity&&Date.now()-(r.activity.time||0)<240000)show(r.activity.message,r.activity.kind);
 }catch(e){show(e.message,'error');}
}
async function saveSource(){
 const reports=ids();if(!reports.length)throw new Error('Choose at least one metric.');
 const spec=parseDashboardUrl($('dashboardUrl').value.trim());
 await send('SAVE_PICKER',{dashboardUrl:spec.url,reports});
 return spec;
}
async function fetchSelected(){if(working)return false;busy(true);try{
 const spec=await saveSource();const from=$('dateFrom').value,to=$('dateTo').value;
 const result=await send('SYNC_PICKED',{reports:ids(),from,to});
 lastDataKey='';await loadState();
 switchView('results');show(`${prettyCount(result.rows)} records merged across ${result.reports} report ${result.reports===1?'category':'categories'}. Review and download below.`,'success');return true;
 }catch(e){show(e.message,'error');return false;}finally{busy(false);await loadState();}
}
async function exportNow(format){try{
 const choice=normalizeSelection(selection),types=ids();const spec=parseDashboardUrl($('dashboardUrl').value.trim());
 const datasets=await allReportRows(spec.datasetKey);
 const from=$('dateFrom').value,to=$('dateTo').value;
 const picked=rowsForExport(datasets,choice,filterConfig());
 // Never export records outside the date range shown in the header.
 const selected=Object.fromEntries(types.map(id=>[id,(picked[id]||[]).filter(row=>row.date>=from&&row.date<=to)]));
 if(types.some(id=>!(selected[id]||[]).length))throw new Error('One selected section has no saved data for these dates. Click Get data first or change the date range.');
 const dateList=types.flatMap(id=>selected[id].map(x=>x.date)).sort();
 const base=`Smart-Export-Selected-${istToday()}`;
 if(format==='csv'||format==='csvzip'){
  const entries=types.flatMap(id=>choice[id].map(field=>({
   name:`${id}-${field}.csv`,csv:selectedCsv(id,selected[id],{[id]:[field]})
  })));
  if(entries.length===1){
   download(new Blob([entries[0].csv],{type:'text/csv;charset=utf-8'}),`${base}-${entries[0].name}`);
  }else{
   if(format==='csv')throw new Error('Choose Individual CSV files to export multiple parameters.');
   download(new Blob([buildCsvZip(entries)],{type:'application/zip'}),`${base}-Individual-CSV-Parameters.zip`);
  }
 }else{
  const wb=buildPickedWorkbook(selected,{selection:choice,from:dateList[0],to:dateList.at(-1),filter:filterConfig(),perMetricSheets:true});
  download(wb,`${base}.xlsx`);
 }
 show(`${format==='csvzip'?'Individual CSV files':format.toUpperCase()} downloaded. Your saved master was not changed.`,'success');
 }catch(e){show(e.message,'error');}
}
async function toggleSchedule(){const enabled=$('autoDaily').checked;try{
 await saveSource();const r=await send('ENABLE_PICKED',{enabled,reports:ids()});config={...config,...r.config};
 show(enabled?'Daily updates enabled for your selected categories. Chrome and signed-in Grafana must remain available.':'Automatic updates paused.','success');
 await loadState();
 }catch(e){$('autoDaily').checked=!enabled;show(e.message,'error');}
}
function updateSavedList(){
 const select=$('savedPresets'),current=select.value;select.replaceChildren();
 const first=document.createElement('option');first.value='';first.textContent='Choose a saved view…';select.append(first);
 for(const name of Object.keys(savedViews).sort((a,b)=>a.localeCompare(b))){const o=document.createElement('option');o.value=name;o.textContent=name;select.append(o);}if(savedViews[current])select.value=current;
}
async function savePreset(){try{
 const name=$('presetName').value.trim();if(!name||name.length>40)throw new Error('Give your saved view a name (up to 40 characters).');
 if(ids().length===0)throw new Error('Select metrics before saving a view.');
 const sameName=Object.keys(savedViews).find(x=>x.toLocaleLowerCase()===name.toLocaleLowerCase());
 if(sameName){if(!confirm(`Replace your existing view “${sameName}”?`))return;delete savedViews[sameName];}
 if(Object.keys(savedViews).length>=20)throw new Error('Maximum 20 saved views. Delete one before creating another.');
 savedViews[name]=normalizeSelection(selection);await chrome.storage.local.set({[VIEWS]:savedViews});updateSavedList();$('savedPresets').value=name;show(`Saved view “${name}”.`,'success');
 }catch(e){show(e.message,'error');}
}
async function loadPreset(){const key=$('savedPresets').value;if(!savedViews[key]){show('Choose a saved view first.','warning');return;}await setSelection(savedViews[key],{announce:true});switchView('build');}
async function deletePreset(){const key=$('savedPresets').value;if(!savedViews[key]){show('Choose a saved view first.','warning');return;}if(!confirm(`Delete saved view “${key}”?`))return;delete savedViews[key];await chrome.storage.local.set({[VIEWS]:savedViews});updateSavedList();show('Saved view deleted.','success');}
async function scanPanels(){
 try{
  const browser=$('panelBrowser');browser.textContent='Scanning the signed-in dashboard…';
  await saveSource();const data=await send('SCAN_DASHBOARD_PANELS');
  const groups=new Map();for(const p of data.panels||[]){const key=p.section||'Other panels';if(!groups.has(key))groups.set(key,[]);groups.get(key).push(p);}
  browser.replaceChildren();
  for(const [section,panels] of groups){
   const group=document.createElement('div');group.className='panel-group';
   const title=document.createElement('strong');title.textContent=`${section} · ${panels.length} panels`;group.append(title);
   for(const p of panels){const row=document.createElement('div');row.className='panel-item';
    const label=document.createElement('span');label.textContent=p.title;
    const status=document.createElement('span');status.className='panel-status'+(p.mapped?'':' unmapped');status.textContent=p.mapped?'Source mapped':'Not mapped';
    row.append(label,status);group.append(row);
   }
   browser.append(group);
  }
  if(!groups.size)browser.textContent='No panels found on the selected dashboard.';
  show(`Found ${(data.panels||[]).length} live dashboard panels. Only verified parameters can be exported automatically.`, 'success');
 }catch(e){$('panelBrowser').textContent='Panel scan failed. Use Download error logs or check Grafana sign-in.';show(e.message,'error');}
}
async function init(){
 const stored=await chrome.storage.local.get({[STORE]:DEFAULT_SELECTION,[VIEWS]:{},[UI_VIEW]:'build'});
 try{selection=normalizeSelection(stored[STORE]);}catch{selection=normalizeSelection(DEFAULT_SELECTION);}
 savedViews=typeof stored[VIEWS]==='object'&&stored[VIEWS]&&!Array.isArray(stored[VIEWS])?stored[VIEWS]:{};
 bindNavigation();switchView(stored[UI_VIEW],{remember:false});
 $('moreTemplates').addEventListener('click',()=>{const expanded=$('quickPicks').classList.toggle('expanded');$('moreTemplates').setAttribute('aria-expanded',String(expanded));$('moreTemplates').innerHTML=expanded?'Show fewer templates <span aria-hidden="true">⌃</span>':'Show more templates <span aria-hidden="true">⌄</span>';});
 presetDates(7);draw();updateSavedList();await loadState({showActivity:true});
 $('metricSearch').addEventListener('input',()=>{const host=$('metricCatalog');host.scrollTop=0;renderCatalog();});
 $('clearSearch').addEventListener('click',()=>{$('metricSearch').value='';renderCatalog();$('metricSearch').focus();});
 $('dashboardUrl').addEventListener('input',()=>{updateStats();updateButtons();});
 $('useCurrent').addEventListener('click',async()=>{try{const r=await send('CURRENT_GRAFANA_TAB');$('dashboardUrl').value=r.url;await saveSource();await loadState();show('Current signed-in Grafana dashboard selected.','success');}catch(e){show(e.message,'error');}});
 $('last7').addEventListener('click',()=>presetDates(7));$('last30').addEventListener('click',()=>presetDates(30));
 for(const id of ['dateFrom','dateTo'])$(id).addEventListener('input',()=>{for(const size of [7,30]){const b=$(size===7?'last7':'last30');b.classList.remove('is-active');b.setAttribute('aria-pressed','false');}});
 $('syncNow').addEventListener('click',fetchSelected);
 $('dockFetch').addEventListener('click',fetchSelected);
 $('dockExcel').addEventListener('click',()=>exportNow('xlsx'));
 $('downloadXlsx').addEventListener('click',()=>exportNow('xlsx'));
 $('downloadCsv').addEventListener('click',()=>exportNow('csv'));
 $('autoDaily').addEventListener('change',toggleSchedule);
 $('filterField').addEventListener('change',()=>{filter.field=$('filterField').value;renderPreview();});
 $('filterText').addEventListener('input',()=>{filter.text=$('filterText').value;renderPreview();});
 $('savePreset').addEventListener('click',savePreset);$('loadPreset').addEventListener('click',loadPreset);$('deletePreset').addEventListener('click',deletePreset);
 $('classic').addEventListener('click',()=>chrome.tabs.create({url:chrome.runtime.getURL('legacy-popup.html')}));
 $('scanPanels').addEventListener('click',scanPanels);
 $('feedbackHelp')?.addEventListener('click',()=>{
   switchView('automation');$('advancedSettings').open=true;
   $('advancedSettings').scrollIntoView({block:'nearest',behavior:'smooth'});
 });
 $('feedbackDismiss')?.addEventListener('click',()=>{
   const wrap=$('feedback')?.closest('.feedback-wrap');if(wrap)wrap.dataset.kind='info';
   $('feedbackHelp').hidden=true;$('feedbackDismiss').hidden=true;
 });
 $('logs').addEventListener('click',async()=>{try{const x=await send('EXPORT_LOGS');download(new Blob([JSON.stringify({product:'Smart Export v2.6.0',exportedAt:new Date().toISOString(),logs:x.logs},null,2)],{type:'application/json'}),'Smart-Export-Errors.json');show('Diagnostics downloaded. Please review them before sharing.','success');}catch(e){show(e.message,'error');}});
 $('clearData').addEventListener('click',async()=>{if(!confirm('Delete the saved v2 report master for this Grafana dashboard? Export Excel first.'))return;if(!confirm('Are you sure? The existing GEO v1 master will remain untouched.'))return;try{await send('CLEAR_V2');lastDataKey='';allData={};await loadState();show('Saved v2 master cleared. Legacy GEO data preserved.','success');}catch(e){show(e.message,'error');}});
 chrome.storage.onChanged.addListener(ch=>{if(ch.smartExportActivity||ch.smartExportConfig)loadState().catch(()=>{});});
}
// Internal, UI-only facade. This exposes the existing certified reporting engine
// to the modern parameter studio without fragile DOM click/search simulation.
// No credentials, session tokens, or extra network privileges are exposed.
const bridge = {
 ready:false,
 getSelection:()=>normalizeSelection(selection,{allowEmpty:true}),
 setSelection:async next=>setSelection(next),
 getDates:()=>({from:$('dateFrom').value,to:$('dateTo').value}),
 setDates:({from,to})=>{
   $('dateFrom').value=from;$('dateTo').value=to;
   for(const size of [7,30]){
     const btn=$(size===7?'last7':'last30');btn.classList.remove('is-active');btn.setAttribute('aria-pressed','false');
   }
 },
 getDashboardUrl:()=>$('dashboardUrl').value,
 useGrafana:async()=>{
   const result=await send('CURRENT_GRAFANA_TAB');
   $('dashboardUrl').value=result.url;
   // A user must be able to connect Grafana before choosing metrics.
   // SAVE_PICKER requires a nonempty report selection, so defer saving until
   // a first metric is chosen/fetched rather than making Connect fail.
   if(ids().length){await saveSource();await loadState();}
   else {updateStats();updateButtons();}
   return result.url;
 },
 backGrafana:()=>document.getElementById('openGrafana')?.click(),
 isBusy:()=>working,
 fetch:()=>fetchSelected(),
 export:format=>exportNow(format),
 showView:view=>switchView(view),
};
window.SmartExportBridge=bridge;
init().then(()=>{bridge.ready=true;window.dispatchEvent(new Event('smart-export-ready'));})
      .catch(e=>{show(e.message,'error');window.dispatchEvent(new Event('smart-export-error'));});


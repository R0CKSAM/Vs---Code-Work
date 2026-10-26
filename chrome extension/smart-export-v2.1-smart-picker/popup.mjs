/* Smart Export v2.1 — approachable metric picker on top of fixed, verified report templates.
   This file runs in the popup; background querying is kept separate. */
import {DEFAULT_CONFIG,parseDashboardUrl,datesForLastCompleteDays,istToday} from './core.mjs';
import {REPORT_ORDER,REPORTS} from './reports.mjs';
import {GROUPS,DETAILS,FIELD_LABELS,PRESETS,DEFAULT_SELECTION,normalizeSelection,selectedColumns,selectionCounts,selectionReports} from './metric-catalog.mjs';
import {allReportRows} from './report-db.mjs';
import {buildPickedWorkbook} from './multi-xlsx.mjs';
import {rowsForExport,selectedCsv} from './picked-export.mjs';

const $=id=>document.getElementById(id);
const STORE='smartExportSmartPicker_v21',VIEWS='smartExportSavedViews_v21';
let selection=normalizeSelection(DEFAULT_SELECTION),working=false,config={...DEFAULT_CONFIG};
let summaries={},coverage={},allData={},savedViews={},lastDataKey='',latestActivity=null,filter={field:'',text:''};
let activePreset='overview';
const send=(type,args={})=>new Promise((resolve,reject)=>chrome.runtime.sendMessage({type,...args},res=>{
 if(chrome.runtime.lastError)return reject(new Error(chrome.runtime.lastError.message));
 if(!res)return reject(new Error('Smart Export is not responding. Reload the extension in Chrome.'));
 if(!res.ok)return reject(new Error(res.error||'Unknown Grafana export error.'));
 resolve(res.data);
}));
const show=(value,kind='info')=>{const el=$('feedback');el.textContent=String(value);el.className='feedback '+(kind==='warning'?'warn':kind==='error'?'error':kind==='success'?'success':'');};
const dateStamp=ts=>{if(!ts)return 'Never';try{return new Date(ts).toLocaleString('en-IN',{dateStyle:'medium',timeStyle:'short',timeZone:'Asia/Kolkata'});}catch{return '—';}};
const presetDates=n=>{const r=datesForLastCompleteDays(n);$('dateFrom').value=r.from;$('dateTo').value=r.to;};
const identical=(a,b)=>JSON.stringify(normalizeSelection(a,{allowEmpty:true}))===JSON.stringify(normalizeSelection(b,{allowEmpty:true}));
const ids=()=>selectionReports(selection);
const prettyCount=n=>Number(n||0).toLocaleString('en-IN');
const download=(blob,name)=>{const u=URL.createObjectURL(blob),a=document.createElement('a');a.href=u;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),45000);};
function busy(isBusy){working=!!isBusy;
 for(const id of ['useCurrent','syncNow','autoDaily','last7','last30','savePreset','loadPreset','deletePreset'])$(id).disabled=working;
 $('syncLabel').textContent=working?'Fetching your numbers…':'Fetch selected data';
 $('dockFetch').textContent=working?'Fetching…':'Fetch data →';
 updateButtons();
}
function updateButtons(){
 const types=ids(),ready=types.length&&types.every(id=>Number(summaries[id]?.rows)>0);
 $('downloadXlsx').disabled=working||!ready;
 $('downloadCsv').disabled=working||!ready||types.length!==1;
 $('downloadCsv').title=types.length!==1?'CSV supports one report category. Excel contains a tab for each selected category.':'';
 $('syncNow').disabled=working||!types.length;
 $('dockFetch').disabled=working||!types.length;
 $('dockExcel').disabled=working||!ready;
}
function renderQuickPicks(){
 const host=$('quickPicks');host.replaceChildren();
 for(const [key,p] of Object.entries(PRESETS)){
  const b=document.createElement('button');b.type='button';b.className='quick-btn';b.dataset.preset=key;
  b.setAttribute('aria-pressed',String(identical(selection,p.selection)));
  if(identical(selection,p.selection)){b.classList.add('active');activePreset=key;}
  const label=document.createElement('strong');label.textContent=p.title;
  const sub=document.createElement('small');sub.textContent=p.hint;
  b.append(label,sub);b.addEventListener('click',()=>setSelection(p.selection,{announce:true}));
  host.append(b);
 }
}
function renderCatalog(){
 const host=$('metricCatalog'),needle=$('metricSearch').value.trim().toLocaleLowerCase(),selected=normalizeSelection(selection,{allowEmpty:true});
 const oldOpen=[...host.querySelectorAll('details[open]')].map(x=>x.dataset.report);
 host.replaceChildren();let visible=0;
 for(const id of REPORT_ORDER){
  const group=GROUPS[id],matches=REPORTS[id].metrics.filter(field=>!needle||
    [group.title,group.section,group.short,field,DETAILS[field]?.label,DETAILS[field]?.help].some(s=>String(s||'').toLocaleLowerCase().includes(needle)));
  if(!matches.length)continue;visible++;
  const root=document.createElement('details');root.className='metric-category';root.dataset.report=id;
  root.open=!!needle||oldOpen.includes(id)||((selected[id]?.length||0)>0&&oldOpen.length===0);
  const summary=document.createElement('summary');
  const ic=document.createElement('span');ic.className='category-icon';ic.textContent=group.icon;
  const text=document.createElement('span');text.className='category-body';
  const heading=document.createElement('strong');heading.textContent=group.title;
  const sub=document.createElement('small');sub.textContent=group.short;
  text.append(heading,sub);
  const count=document.createElement('span');count.className='category-num';count.textContent=`${selected[id]?.length||0}/${REPORTS[id].metrics.length}`;
  const caret=document.createElement('span');caret.className='category-caret';caret.textContent='⌄';caret.setAttribute('aria-hidden','true');
  summary.append(ic,text,count,caret);
  const body=document.createElement('div');body.className='metric-choices';
  for(const field of matches){
   const label=document.createElement('label');label.className='metric-item';
   const checked=!!selected[id]?.includes(field);if(checked)label.classList.add('checked');
   const check=document.createElement('input');check.type='checkbox';check.checked=checked;check.dataset.report=id;check.dataset.metric=field;check.setAttribute('aria-label',`${DETAILS[field]?.label||field} (${group.title})`);
   check.addEventListener('change',()=>toggleMetric(id,field,check.checked));
   const copy=document.createElement('span');copy.className='metric-copy';
   const strong=document.createElement('strong');strong.textContent=DETAILS[field]?.label||field;
   const small=document.createElement('small');small.textContent=DETAILS[field]?.help||'';
   copy.append(strong,small);label.append(check,copy);body.append(label);
  }
  root.append(summary,body);host.append(root);
 }
 if(!visible){const p=document.createElement('p');p.className='nothing';p.textContent='No matching parameter. Try “users”, “views”, “channel”, or “playtime”.';host.append(p);}
}
function renderSelected(){
 const choice=normalizeSelection(selection,{allowEmpty:true}),stats=selectionCounts(choice),host=$('selectedChips');host.replaceChildren();
 $('selectedCount').textContent=`${stats.metrics} metric${stats.metrics===1?'':'s'}`;
 $('sourceCount').textContent=stats.reports;
 $('sheetHint').textContent=stats.reports===0?'Choose a metric':stats.reports===1?'One Excel report tab':`${stats.reports} Excel tabs, no unsafe joins`;
 for(const id of REPORT_ORDER)for(const field of choice[id]||[]){
  const item=document.createElement('div');item.className='selected-chip';
  const text=document.createElement('span');text.textContent=`${GROUPS[id].title}: ${DETAILS[field]?.label||field}`;
  const remove=document.createElement('button');remove.type='button';remove.textContent='×';remove.setAttribute('aria-label',`Remove ${text.textContent}`);remove.addEventListener('click',()=>toggleMetric(id,field,false));
  item.append(text,remove);host.append(item);
 }
 if(!stats.metrics){const empty=document.createElement('span');empty.className='subtext';empty.textContent='Your selection will appear here.';host.append(empty);}
}
function draw(){renderQuickPicks();renderCatalog();renderSelected();renderFilter();renderPreview();updateButtons();}
async function saveChoice(){await chrome.storage.local.set({[STORE]:selection});}
async function setSelection(input,{announce=false}={}){
 selection=normalizeSelection(input,{allowEmpty:true});
 await saveChoice();draw();
 if(config.enabled&&config.autoReport==='picked'&&!sameReports(ids(),config.autoReports||[])){
  try{const old=config.autoReports?.length?config.autoReports:ids();await send('ENABLE_PICKED',{enabled:false,reports:old});config.enabled=false;$('autoDaily').checked=false;show('Your scheduled categories changed. Daily updates have been paused until you review the new selection.','warning');}
  catch(e){show('Could not pause the old scheduled selection: '+e.message,'error');}
 }
 if(announce)show(`${selectionCounts(selection).metrics} metrics selected. Pick dates and fetch the data.`, 'success');
}
const sameReports=(a,b)=>JSON.stringify(REPORT_ORDER.filter(id=>a.includes(id)))===JSON.stringify(REPORT_ORDER.filter(id=>b.includes(id)));
function toggleMetric(id,field,checked){
 const choice=normalizeSelection(selection,{allowEmpty:true}),set=new Set(choice[id]||[]);
 if(checked)set.add(field);else set.delete(field);
 if(set.size)choice[id]=REPORTS[id].metrics.filter(x=>set.has(x));else delete choice[id];
 setSelection(choice);
}
function renderFilter(){
 const host=$('exportFilterBox'),selected=ids();
 if(selected.length!==1){host.hidden=true;filter={field:'',text:''};$('filterText').value='';return;}
 const report=REPORTS[selected[0]],dims=report.dimension.filter(x=>x!=='date');
 host.hidden=!dims.length;
 const field=$('filterField');field.replaceChildren();
 for(const key of dims){const opt=document.createElement('option');opt.value=key;opt.textContent=FIELD_LABELS[key]||key;field.append(opt);}
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
 if(!eligible){$('previewScroll').hidden=false;table.hidden=true;$('previewEmpty').hidden=false;$('previewName').textContent='Preview of selected fields';$('previewMeta').textContent='Not fetched';return;}
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
 const ready=reports.length&&reports.every(id=>summaries[id]?.rows);
 const status=$('stateChip');status.textContent=working?'FETCHING':config.enabled?'DAILY ON':ready?'READY TO EXPORT':'NOT FETCHED';
 status.className='state-chip '+(working?'working':config.enabled?'':'warn');
 $('autoDaily').checked=!!config.enabled&&!!config.v2Mode&&config.autoReport==='picked'&&sameReports(reports,config.autoReports||[]);
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
async function fetchSelected(){if(working)return;busy(true);try{
 const spec=await saveSource();const from=$('dateFrom').value,to=$('dateTo').value;
 const result=await send('SYNC_PICKED',{reports:ids(),from,to});
 lastDataKey='';await loadState();
 show(`${prettyCount(result.rows)} records merged across ${result.reports} report ${result.reports===1?'category':'categories'}. Choose Excel or CSV below.`,'success');
 }catch(e){show(e.message,'error');}finally{busy(false);await loadState();}
}
async function exportNow(format){try{
 const choice=normalizeSelection(selection),types=ids();const spec=parseDashboardUrl($('dashboardUrl').value.trim());
 const datasets=await allReportRows(spec.datasetKey);const selected=rowsForExport(datasets,choice,filterConfig());
 if(types.some(id=>!(selected[id]||[]).length))throw new Error('One selected category has no matching stored data. Fetch it or remove the filter.');
 const dateList=types.flatMap(id=>selected[id].map(x=>x.date)).sort();
 const base=`Smart-Export-Selected-${istToday()}`;
 if(format==='csv'){
  if(types.length!==1)throw new Error('CSV supports one category. Use Excel for several category tabs.');
  download(new Blob([selectedCsv(types[0],selected[types[0]],choice)],{type:'text/csv;charset=utf-8'}),`${base}.csv`);
 }else{
  const wb=buildPickedWorkbook(selected,{selection:choice,from:dateList[0],to:dateList.at(-1),filter:filterConfig()});
  download(wb,`${base}.xlsx`);
 }
 show(`${format.toUpperCase()} downloaded. Your saved master was not changed.`,'success');
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
async function loadPreset(){const key=$('savedPresets').value;if(!savedViews[key]){show('Choose a saved view first.','warning');return;}await setSelection(savedViews[key],{announce:true});}
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
 const stored=await chrome.storage.local.get({[STORE]:DEFAULT_SELECTION,[VIEWS]:{}});
 try{selection=normalizeSelection(stored[STORE]);}catch{selection=normalizeSelection(DEFAULT_SELECTION);}
 savedViews=typeof stored[VIEWS]==='object'&&stored[VIEWS]&&!Array.isArray(stored[VIEWS])?stored[VIEWS]:{};
 presetDates(7);draw();updateSavedList();await loadState({showActivity:true});
 $('metricSearch').addEventListener('input',renderCatalog);
 $('clearSearch').addEventListener('click',()=>{$('metricSearch').value='';renderCatalog();$('metricSearch').focus();});
 $('useCurrent').addEventListener('click',async()=>{try{const r=await send('CURRENT_GRAFANA_TAB');$('dashboardUrl').value=r.url;await saveSource();await loadState();show('Current signed-in Grafana dashboard selected.','success');}catch(e){show(e.message,'error');}});
 $('last7').addEventListener('click',()=>presetDates(7));$('last30').addEventListener('click',()=>presetDates(30));
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
 $('logs').addEventListener('click',async()=>{try{const x=await send('EXPORT_LOGS');download(new Blob([JSON.stringify({product:'Smart Export v2.1',exportedAt:new Date().toISOString(),logs:x.logs},null,2)],{type:'application/json'}),'Smart-Export-Errors.json');show('Diagnostics downloaded. Please review them before sharing.','success');}catch(e){show(e.message,'error');}});
 $('clearData').addEventListener('click',async()=>{if(!confirm('Delete the saved v2 report master for this Grafana dashboard? Export Excel first.'))return;if(!confirm('Are you sure? The existing GEO v1 master will remain untouched.'))return;try{await send('CLEAR_V2');lastDataKey='';allData={};await loadState();show('Saved v2 master cleared. Legacy GEO data preserved.','success');}catch(e){show(e.message,'error');}});
 chrome.storage.onChanged.addListener(ch=>{if(ch.smartExportActivity||ch.smartExportConfig)loadState().catch(()=>{});});
}
init().catch(e=>show(e.message,'error'));

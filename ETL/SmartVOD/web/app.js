'use strict';
const fields={title:'Titles',category:'Categories',video_key:'Video keys',device_id:'Device ID',cli_ip:'Client IP',os:'Operating system',region:'Region',isp:'ISP / ASN',device_type:'Device type',identity_confidence:'Identity confidence',title_status:'Title quality'};
const $=id=>document.getElementById(id),fmt=(n,d=0)=>Number(n||0).toLocaleString('en-IN',{maximumFractionDigits:d});
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let meta,draft={},applied=null,current=null,options=[],offset=0,facetVersion=0,queryVersion=0,trigger=null,timer,pickerSelection=null,appliedStatus='';
Object.keys(fields).forEach(k=>draft[k]=new Set());
let activityTimer,slowActivityTimer;
function setActivity(state,text){
 clearTimeout(activityTimer);clearTimeout(slowActivityTimer);
 const node=$('activityFeedback');node.hidden=!state;node.dataset.state=state||'';
 $('activityText').textContent=text||'';$('retryResults').hidden=state!=='error';
 if(state==='loading')slowActivityTimer=setTimeout(()=>{if(node.dataset.state==='loading')$('activityText').textContent='Still updating. Please wait...'},4000);
 if(state==='success')activityTimer=setTimeout(()=>{node.hidden=true},1800);
}
$('retryResults').onclick=()=>{if(meta?.dates?.length)apply();else location.reload()};
const request=async(path,body)=>{
 const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),120000);
 try{
  const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:controller.signal});
  if(!r.ok){let e;try{e=await r.json()}catch{e={}}throw Error(e.error||'The request could not be completed. Please retry.')}
  return r;
 }catch(e){
  if(e.name==='AbortError')throw Error('This is taking too long. Try a smaller date range or retry.');
  if(e instanceof TypeError)throw Error('Connection lost. Check that the dashboard service is running, then retry.');
  throw e;
 }finally{clearTimeout(timeout)}
};
function selection(){return {identity_basis:'device_id',filters:Object.fromEntries(Object.entries(draft).map(([k,v])=>[k,[...v].sort()])),start:$('start').value,end:$('end').value,timeStart:$('timeStart').value,timeEnd:$('timeEnd').value}}
function hasPendingChanges(){return !applied||JSON.stringify(selection())!==JSON.stringify(applied)}
function syncPending(){
 const pending=hasPendingChanges();
 $('export').disabled=pending||$('apply').disabled;
 $('export').title=pending?'Apply pending changes before exporting':'Export the applied results';
 $('status').textContent=pending?'Pending changes - Apply filters to update the results':appliedStatus;
 $('advancedPending').hidden=!pending||!applied;
 $('drawerApplyNote').textContent=$('apply').disabled?'Updating results...':pending?'Changes are not applied yet. Use Apply filters.':'All filters are applied.';
}
function showError(message){$('error').textContent=message;$('error').hidden=false;$('drawerError').textContent=message;$('drawerError').hidden=false}
function dirty(){renderFilters();syncPending()}
function renderFilters(){window.syncDateRange?.();const count=Object.entries(draft).filter(([k,v])=>k!=='title'&&v.size).length+Number($('timeStart').value!=='00:00'||$('timeEnd').value!=='23:59');$('advancedCount').hidden=!count;$('advancedCount').textContent=count;for(const[k,label]of Object.entries(fields)){const b=$('filter-'+k),s=draft[k];b.classList.toggle('active',!!s.size);b.querySelector('.value').textContent=s.size===1?[...s][0]:s.size?`${s.size} selected`:({title:'All titles',category:'All categories',video_key:'All video keys',device_id:'All device IDs',cli_ip:'All client IPs',os:'All OS versions',region:'All regions',isp:'All ISPs / ASNs',device_type:'All device types',identity_confidence:'All identity confidence',title_status:'All title quality'}[k]);}$('chips').innerHTML='';for(const[k,s]of Object.entries(draft)){if(s.size){const b=document.createElement('button');b.className='chip';b.textContent=`${fields[k]}: ${s.size} selected - Clear`;b.onclick=()=>{s.clear();dirty()};$('chips').append(b)}}}
for(const[k,label]of Object.entries(fields)){const box=document.createElement('div');box.className='field';box.innerHTML=`<label id="label-${k}">${label}</label><button id="filter-${k}" class="filter-trigger" aria-haspopup="dialog" aria-labelledby="label-${k} filter-${k}" aria-expanded="false"><span class="value"></span><span class="chevron">▾</span></button>`;(k==='title'?$('filters'):$('advancedFilters')).append(box);$('filter-'+k).onclick=()=>openPicker(k)}



function openPicker(k){if(!$('picker').hidden)closePicker();$('rangePicker').open=false;current=k;pickerSelection=new Set(draft[k]);document.body.classList.add('picker-open');document.querySelector('main').inert=true;$('advancedDrawer').inert=true;trigger=$('filter-'+k);trigger.setAttribute('aria-expanded','true');$('pickerTitle').textContent=fields[k];$('done').textContent=k==='title'?'Apply title':'Done';$('pickerHelp').textContent=k==='title'?'Choose titles, then Apply title to update results.':'Choose options, then Done. Apply filters in the menu updates results.';$('search').value='';offset=0;options=[];$('picker').hidden=false;$('scrim').hidden=false;const r=trigger.getBoundingClientRect();$('picker').style.left=Math.max(12,Math.min(r.left,innerWidth-432))+'px';$('picker').style.top=Math.max(14,Math.min(r.bottom+8,innerHeight-510))+'px';$('search').focus();loadOptions()}
function closePicker(commit=false){
 clearTimeout(timer);facetVersion++;
 if(current&&!commit&&pickerSelection)draft[current]=new Set(pickerSelection);
 $('picker').hidden=true;$('scrim').hidden=true;document.body.classList.remove('picker-open');
 const drawerOpen=document.body.classList.contains('drawer-open');
 document.querySelector('main').inert=drawerOpen;$('advancedDrawer').inert=!drawerOpen;
 if(current){renderFilters();syncPending()}
 if(trigger){trigger.setAttribute('aria-expanded','false');trigger.focus()}
 current=null;pickerSelection=null;
}
async function loadOptions(append=false){
 const version=++facetVersion,field=current;if(!field)return;
 $('options').setAttribute('aria-busy','true');$('selectedCount').textContent=draft[field].size+' selected';
 $('selectVisible').disabled=true;$('loadMore').disabled=true;
 $('loadMore').textContent='Loading...';$('facetFeedback').textContent=append?'Loading more options...':'Searching options...';
 $('facetFeedback').classList.remove('failed');
 if(!append){options=[];offset=0;$('loadMore').hidden=true;$('options').innerHTML='<div class="empty">Searching...</div>'}
 try{
  const r=await(await request('/api/facet',{...selection(),field,search:$('search').value,offset,sort:$('filterSort').value})).json();
  if(version!==facetVersion)return;
  options=append?[...options,...r.options]:r.options;offset=options.length;$('loadMore').hidden=!r.more;renderOptions();
  $('facetFeedback').textContent=options.length?`Showing ${options.length} options${r.more?' - more available':''}.`:'No options match this search.';
 }catch(e){
  if(version===facetVersion){
   if(append)renderOptions();else $('options').innerHTML=`<div class="empty">${esc(e.message)}</div>`;
   $('facetFeedback').textContent=append?'Could not load more options. Try Load more again.':e.message;
   $('facetFeedback').classList.add('failed');
  }
 }finally{
  if(version===facetVersion){$('options').setAttribute('aria-busy','false');$('loadMore').disabled=false;$('loadMore').textContent='Load more options';$('selectVisible').disabled=!options.length}
 }
}
function renderOptions(){const node=$('options');node.innerHTML='';if(!options.length)node.innerHTML='<div class="empty">No matching options. Try another search or clear a filter.</div>';for(const o of options){const label=document.createElement('label');label.className='option';const check=document.createElement('input');check.type='checkbox';check.checked=draft[current].has(o.value);check.onchange=()=>{check.checked?draft[current].add(o.value):draft[current].delete(o.value);$('selectedCount').textContent=draft[current].size+' selected';dirty()};const text=document.createElement('span');text.textContent=o.value;const count=document.createElement('small');count.textContent=$('filterSort').value==='hours'?fmt(o.hours,2)+' h':fmt(o.segments);count.title=$('filterSort').value==='hours'?'Estimated watch hours':'Segment requests';label.append(check,text,count);node.append(label)}}
$('search').oninput=()=>{clearTimeout(timer);timer=setTimeout(()=>loadOptions(),180)};$('loadMore').onclick=()=>loadOptions(true);$('selectVisible').onclick=()=>{for(const o of options)draft[current].add(o.value);renderOptions();$('selectedCount').textContent=draft[current].size+' selected';dirty()};$('clearField').onclick=()=>{draft[current].clear();renderOptions();$('selectedCount').textContent='0 selected';dirty()};$('closePicker').onclick=$('cancelPicker').onclick=$('scrim').onclick=()=>closePicker();
document.addEventListener('keydown',e=>{if($('picker').hidden)return;if(e.key==='Escape'){closePicker();return}if(e.key==='Tab'){const nodes=[...$('picker').querySelectorAll('button,input,select')].filter(n=>!n.hidden&&!n.disabled&&n.getClientRects().length),first=nodes[0],last=nodes.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus()}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus()}}});
for(const id of ['start','end','timeStart','timeEnd'])$(id).onchange=dirty;
function renderDeliveryStatuses(data){
 const rows=data.delivery_statuses||[],total=rows.reduce((n,r)=>n+r.requests,0);
 const share=count=>count>0&&count/total*100<0.01?'&lt;0.01%':fmt(total?count/total*100:0,2)+'%';
 const descriptions={'200':'OK','201':'Created','202':'Accepted','204':'No Content','206':'Partial Content','301':'Moved Permanently','302':'Found','304':'Not Modified','307':'Temporary Redirect','308':'Permanent Redirect','400':'Bad Request','401':'Unauthorized','403':'Forbidden','404':'Not Found','405':'Method Not Allowed','408':'Request Timeout','410':'Gone','416':'Range Not Satisfiable','429':'Too Many Requests','500':'Internal Server Error','502':'Bad Gateway','503':'Service Unavailable','504':'Gateway Timeout'};
 const sorted=[...rows].sort((a,b)=>(a.code==='Unknown'?1000:Number(a.code))-(b.code==='Unknown'?1000:Number(b.code)));
 $('deliveryStatuses').innerHTML=!data.delivery_status_available?'<p class="note">Status breakdown will be available after the data snapshot refresh.</p>':!total?'<p class="note">No segment requests in this selection.</p>':'<table class="delivery-table" aria-label="HTTP response code breakdown"><thead><tr><th scope="col">Code</th><th scope="col">Response</th><th scope="col">Requests</th><th scope="col">Share</th><th scope="col">Watch hours</th></tr></thead><tbody>'+sorted.map(r=>`<tr class="status-code" data-code="${esc(r.code)}"><td>${esc(r.code)}</td><td>${esc(descriptions[r.code]||(r.code==='Unknown'?'Missing / invalid code':'HTTP response'))}</td><td>${fmt(r.requests)}</td><td>${share(r.requests)}</td><td>${fmt(r.hours,3)}</td></tr>`).join('')+'</tbody></table>';

}
function render(data){renderDeliveryStatuses(data);$('snapshotHours').textContent=fmt(data.kpi.hours,3)+' h';$('snapshotDelivered').textContent=fmt(data.kpi.delivered,3)+' h';$('averageMinutes').textContent=data.kpi.average_device_minutes==null?'N/A':fmt(data.kpi.average_device_minutes,2);$('averageIPMinutes').textContent=data.kpi.average_ip_minutes==null?'N/A':fmt(data.kpi.average_ip_minutes,2);for(const id of ['hours','devices','ips','videos','segments'])$(id).textContent=fmt(data.kpi[id],id==='hours'?2:0);$('breakdowns').innerHTML='';for(const[k,label]of Object.entries({device_type:'Device type',os:'Operating system',region:'Region',isp:'Internet provider'})){const items=data.breakdown[k],max=Math.max(...items.map(x=>x.hours),1);$('breakdowns').innerHTML+=`<article class="panel breakdown"><h3>${label}<small>Top 5 · estimated hours</small></h3>${items.length?items.map(x=>`<div class="bar-row"><div class="bar-label"><span title="${esc(x.label)}">${esc(x.label)}</span><b>${fmt(x.hours,1)} h</b></div><div class="bar-track"><i style="width:${x.hours/max*100}%"></i></div></div>`).join(''):'<div class="empty">No data</div>'}</article>`}window.renderWatchTrends?.(data);$('table').innerHTML=data.table.length?data.table.map(r=>`<tr><td><b>${esc(r.video_key)}</b><small title="${esc(r.title)}">${esc(r.title)}</small><small>${esc(r.req_host)} &middot; ${esc(r.title_status)}</small></td><td>${fmt(r.hours,3)}</td><td>${fmt(r.delivered,3)}</td><td>${r.average_device_minutes==null?'N/A':fmt(r.average_device_minutes,2)}</td><td>${r.average_ip_minutes==null?'N/A':fmt(r.average_ip_minutes,2)}</td><td>${fmt(r.ips)}</td><td>${fmt(r.devices)}</td></tr>`).join(''):'<tr><td colspan="7" class="empty">No matching data. Change or reset your filters.</td></tr>'}
async function apply(){
 const version=++queryVersion,body=selection();
 $('error').hidden=true;$('drawerError').hidden=true;$('apply').disabled=true;
 document.querySelector('.master-filters').setAttribute('aria-busy','true');
 $('export').disabled=true;$('status').textContent='Updating all metrics...';
 $('results').inert=true;$('results').setAttribute('aria-busy','true');document.body.classList.add('is-updating');
 $('apply').textContent='Updating...';$('drawerApplyNote').textContent='Updating results...';setActivity('loading','Updating results...');
 try{
  if(!body.start||!body.end||body.start>body.end)throw Error('Choose a valid date range.');
  if(!body.timeStart||!body.timeEnd)throw Error('Choose both time values.');
  if(window.isInsightsActive?.()){
   const insight=await window.applyInsightSelection(body);
   if(version!==queryVersion)return false;
   if(!insight)throw Error('Insights could not be refreshed. Your previous applied selection is unchanged. Retry analysis.');
   applied=body;appliedStatus=`Insights applied / ${body.start} to ${body.end} / ${body.timeStart}-${body.timeEnd} IST`;
   setActivity('success','Insights updated');return true;
  }
  const data=await(await request('/api/query',body)).json();
  if(version!==queryVersion)return false;
  render(data);window.renderDevices(data.explorers.device_id,'device_id');window.renderDevices(data.explorers.cli_ip,'cli_ip');
  applied=body;window.loadJourney(body);window.onInsightsApplied?.();
  appliedStatus=`${fmt(data.kpi.records)} matched records · ${body.start} — ${body.end} · ${body.timeStart}–${body.timeEnd} IST${body.timeStart>body.timeEnd?' (overnight window)':''}`;
  const daysRequested=Math.round((Date.parse(body.end)-Date.parse(body.start))/86400000)+1;
  const daysLoaded=meta.dates.filter(d=>d>=body.start&&d<=body.end).length;
  if(daysLoaded<daysRequested)appliedStatus+=' | Some selected dates have no loaded data';
  setActivity('success','Results updated');return true;
 }catch(e){
  if(version!==queryVersion)return false;
  showError(e.message);setActivity('error',e.message);$('status').textContent='Results unchanged - correct the selection and apply again';return false;
 }finally{
  if(version===queryVersion){
   $('apply').disabled=false;$('apply').textContent='Apply filters';document.querySelector('.master-filters').setAttribute('aria-busy','false');
   $('results').inert=false;$('results').setAttribute('aria-busy','false');document.body.classList.remove('is-updating');
   if($('error').hidden)syncPending();else{$('export').disabled=hasPendingChanges();$('drawerApplyNote').textContent='Check the message above, then apply again.';}
  }
 }
}
$('apply').onclick=apply;$('reset').onclick=()=>{window.clearExplorerHistory?.();if(location.hash.startsWith('#view='))history.replaceState(null,'',location.pathname+location.search);Object.values(draft).forEach(s=>s.clear());$('start').value=meta.dates.at(-1);$('end').value=meta.dates.at(-1);$('timeStart').value='00:00';$('timeEnd').value='23:59';renderFilters();apply()};
$('export').onclick=async()=>{if(!applied||hasPendingChanges())return;$('export').disabled=true;try{const r=await request('/api/export',applied),url=URL.createObjectURL(await r.blob()),a=document.createElement('a');a.href=url;a.download=`smartvod_${applied.start}_${applied.end}.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}catch(e){showError(e.message)}finally{$('export').disabled=hasPendingChanges()}};
(async()=>{try{$('export').disabled=true;setActivity('loading','Loading dashboard...');meta=await(await fetch('/api/meta',{signal:AbortSignal.timeout(15000)})).json();if(!Array.isArray(meta.dates)||!meta.dates.length)throw Error('No loaded data');document.querySelector('.master-filters').inert=false;$('start').value=meta.dates[0];$('end').value=meta.dates.at(-1);$('coverage').textContent=`Loaded: ${meta.dates[0]} to ${meta.dates.at(-1)} (${meta.dates.length} days) · IST · Minute-level data`;if(!window.restoreSharedView())$('reset').click()}catch(e){showError('Dashboard data is unavailable. Refresh the page or check that the service is running.');setActivity('error','Dashboard data is unavailable. Please retry.')}})();

$('filterSort').onchange=()=>{if(current)loadOptions()};


// The drawer and quick filters share one draft and one applied query.
function openAdvanced(){
  $('rangePicker').open=false;
  $('advancedDrawer').inert=false;$('advancedDrawer').setAttribute('aria-hidden','false');
  $('drawerBackdrop').hidden=false;$('advancedToggle').setAttribute('aria-expanded','true');
  document.body.classList.add('drawer-open');document.querySelector('main').inert=true;
  $('advancedDrawer').querySelector('.drawer-body').scrollTop=0;
  requestAnimationFrame(()=>requestAnimationFrame(()=>{if(document.body.classList.contains('drawer-open')&&$('picker').hidden)$('closeAdvanced').focus()}));
}
function closeAdvanced(){
  if(!$('picker').hidden)closePicker();
  $('advancedDrawer').inert=true;$('advancedDrawer').setAttribute('aria-hidden','true');
  $('drawerBackdrop').hidden=true;$('advancedToggle').setAttribute('aria-expanded','false');
  document.body.classList.remove('drawer-open');document.querySelector('main').inert=false;
  $('advancedToggle').focus();
}
$('advancedToggle').onclick=openAdvanced;
$('advancedDrawer').addEventListener('transitionend',e=>{if(e.target===$('advancedDrawer')&&e.propertyName==='transform'&&document.body.classList.contains('drawer-open')&&$('picker').hidden)$('closeAdvanced').focus()});
$('closeAdvanced').onclick=$('drawerBackdrop').onclick=closeAdvanced;
$('apply').onclick=async()=>{const committed=await apply();if(committed&&!hasPendingChanges()&&document.body.classList.contains('drawer-open'))closeAdvanced()};
document.addEventListener('keydown',e=>{
  if(!document.body.classList.contains('drawer-open')||!$('picker').hidden)return;
  if(e.key==='Escape'){e.preventDefault();e.stopImmediatePropagation();closeAdvanced();return}
  if(e.key==='Tab'){
    const nodes=[...$('advancedDrawer').querySelectorAll('button,input,select,summary,a')].filter(n=>!n.disabled&&n.getClientRects().length);
    const first=nodes[0],last=nodes.at(-1);
    if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus()}
    else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus()}
  }
},true);

$('done').onclick=()=>{const titleSelected=current==='title';closePicker(true);if(titleSelected)apply()};

// Keep the controls reachable without covering a scrolled journey heading.
const toolbar=document.querySelector('.master-filters');
new ResizeObserver(()=>document.documentElement.style.setProperty('--toolbar-offset',(toolbar.getBoundingClientRect().height+30)+'px')).observe(toolbar);
window.addEventListener('scroll',()=>toolbar.classList.toggle('is-pinned',scrollY>24),{passive:true});

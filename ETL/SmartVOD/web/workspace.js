(()=>{
const el=id=>document.getElementById(id),key='smartvod.savedViews.v1';
let explorerHistory=[];
window.clearExplorerHistory=()=>{explorerHistory=[]};
function views(){try{const value=JSON.parse(localStorage.getItem(key)||'{}');return value&&typeof value==='object'&&!Array.isArray(value)?value:{}}catch{return {}}}
function message(s){el('viewMessage').textContent=s}
function list(){el('savedNames').replaceChildren();for(const name of Object.keys(views()).sort()){const option=document.createElement('option');option.value=name;el('savedNames').append(option)}}
function restore(value){
    if(!value||typeof value!=='object'||!value.filters||typeof value.filters!=='object'||Array.isArray(value.filters))throw Error('Invalid saved filter view');
    for(const field of Object.keys(value.filters)){if(!Object.hasOwn(fields,field)||!Array.isArray(value.filters[field])||value.filters[field].length>1000||value.filters[field].some(v=>typeof v!=='string'))throw Error('Invalid saved filter values')}
    for(const field of ['start','end']){const dateValue=new Date(value[field]+'T00:00:00Z');if(!/^\d{4}-\d{2}-\d{2}$/.test(value[field])||!Number.isFinite(dateValue.getTime())||dateValue.toISOString().slice(0,10)!==value[field])throw Error('Invalid saved dates')}
    if(value.start>value.end)throw Error('Invalid saved date range');
    for(const field of ['timeStart','timeEnd'])if(!/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(value[field]))throw Error('Invalid saved times');
    window.clearExplorerHistory();for(const field of Object.keys(fields))draft[field]=new Set(value.filters[field]||[]);
    for(const field of ['start','end','timeStart','timeEnd'])el(field).value=value[field];
    if(['segments','hours','alpha_asc','alpha_desc'].includes(value.sort))el('filterSort').value=value.sort;
    renderFilters();apply();
}
window.restoreSharedView=()=>{
    el('qualitySummary').textContent=`Title labels are log-derived; conflicting or unverified names remain flagged. Snapshot built ${meta.built_at.slice(0,16).replace('T',' ')}.`;
    if(!location.hash.startsWith('#view='))return false;
    try{restore(JSON.parse(decodeURIComponent(location.hash.slice(6))));message('Shared filters restored; updating results');return true}catch(e){message(e.message);return false}
};
function currentView(){if(!applied)throw Error('Apply filters first');return {...applied,sort:el('filterSort').value}}
el('saveView').onclick=()=>{try{const name=el('savedName').value.trim();if(!name||name.length>100)throw Error('Enter a view name (1–100 characters)');const saved=views();Object.defineProperty(saved,name,{value:currentView(),enumerable:true,configurable:true,writable:true});localStorage.setItem(key,JSON.stringify(saved));list();message('Applied filters saved on this browser')}catch(e){message(e.message)}};
el('loadView').onclick=()=>{try{const saved=views(),name=el('savedName').value;if(!Object.hasOwn(saved,name))throw Error('Choose an existing saved view');restore(saved[name]);message('Saved filters restored; updating results')}catch(e){message(e.message)}};
el('deleteView').onclick=()=>{try{const saved=views();delete saved[el('savedName').value];localStorage.setItem(key,JSON.stringify(saved));list();message('Saved view deleted')}catch(e){message(e.message)}};
el('shareView').onclick=async()=>{try{const url=new URL(location.href);url.hash='view='+encodeURIComponent(JSON.stringify(currentView()));history.replaceState(null,'',url);await navigator.clipboard.writeText(url.href);message('Local view link copied; opens on this machine')}catch(e){message('Copy the view link from the address bar. It includes the applied filter values.')}};
window.renderDevices=(devices,basis)=>{el(basis==='cli_ip'?'ipExplorerLabel':'explorerLabel').textContent=basis==='cli_ip'?'Client IP explorer':'Device explorer';const root=el(basis==='cli_ip'?'ipExplorer':'deviceExplorer');root.replaceChildren();if(!devices.length){root.textContent='No known identifiers in this selection.';return}for(const d of devices){const b=document.createElement('button');b.className='device-card';b.dataset.identityValue=d.identity_value;const title=document.createElement('b');title.textContent=d.identity_value;const info=document.createElement('span');info.textContent=`${Number(d.hours).toFixed(2)} estimated h · ${d.videos} video keys`;const note=document.createElement('small');note.textContent=(basis==='cli_ip'?'Shared-address activity':d.confidence)+' · Open journey';b.append(title,info,note);b.onclick=async()=>{const origin={basis,body:structuredClone(applied),identity:d.identity_value,positions:{device:el('deviceExplorer').scrollTop,ip:el('ipExplorer').scrollTop}};draft[basis]=new Set([d.identity_value]);renderFilters();if(!await apply())return;if(JSON.stringify(origin.body)!==JSON.stringify(applied))explorerHistory.push(origin);el(basis==='cli_ip'?'journeyPanelIP':'journeyPanel').scrollIntoView({behavior:'smooth',block:'start'})};root.append(b)}};

function setSelection(body){
 for(const field of Object.keys(fields))draft[field]=new Set(body.filters[field]||[]);
 for(const field of ['start','end','timeStart','timeEnd'])el(field).value=body[field];
 renderFilters();
}
async function backToExplorer(basis){
 const button=el(basis==='cli_ip'?'backToIPs':'backToDevices');button.disabled=true;
 try{
  const index=explorerHistory.findLastIndex(entry=>entry.basis===basis),origin=index>=0?explorerHistory[index]:null;
  const before=structuredClone(selection()),body=origin?structuredClone(origin.body):structuredClone(applied);
  if(!body)return;
  if(!origin)body.filters[basis]=[];
  if(JSON.stringify(body)!==JSON.stringify(applied)){
   setSelection(body);
   if(!await apply()){setSelection(before);syncPending();return}
  }
  if(origin)explorerHistory=explorerHistory.slice(0,index);
  if(origin){el('deviceExplorer').scrollTop=origin.positions.device;el('ipExplorer').scrollTop=origin.positions.ip}
  const root=el(basis==='cli_ip'?'ipExplorer':'deviceExplorer');
  const card=[...root.querySelectorAll('.device-card')].find(node=>node.dataset.identityValue===origin?.identity)||root.querySelector('.device-card');
  card?.focus({preventScroll:true});
  el(basis==='cli_ip'?'ipPanel':'devicePanel').scrollIntoView({behavior:'smooth',block:'start'});
 }finally{button.disabled=false}
}
el('backToDevices').onclick=()=>backToExplorer('device_id');
el('backToIPs').onclick=()=>backToExplorer('cli_ip');
list();
})();

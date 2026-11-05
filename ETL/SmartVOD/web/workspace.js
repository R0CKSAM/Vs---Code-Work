(()=>{
const el=id=>document.getElementById(id),key='smartvod.savedViews.v1';
function views(){try{return JSON.parse(localStorage.getItem(key)||'{}')}catch{return {}}}
function message(s){el('viewMessage').textContent=s}
function list(){el('savedNames').replaceChildren();for(const name of Object.keys(views()).sort()){const option=document.createElement('option');option.value=name;el('savedNames').append(option)}}
function restore(value){
    if(!value||typeof value!=='object'||!value.filters||typeof value.filters!=='object')throw Error('Invalid saved filter view');
    for(const field of Object.keys(value.filters)){if(!(field in fields)||!Array.isArray(value.filters[field])||value.filters[field].length>1000||value.filters[field].some(v=>typeof v!=='string'))throw Error('Invalid saved filter values')}
    for(const field of ['start','end'])if(!/^\d{4}-\d{2}-\d{2}$/.test(value[field]))throw Error('Invalid saved dates');
    for(const field of ['timeStart','timeEnd'])if(!/^\d{2}:\d{2}$/.test(value[field]))throw Error('Invalid saved times');
    for(const field of Object.keys(fields))draft[field]=new Set(value.filters[field]||[]);
    for(const field of ['start','end','timeStart','timeEnd'])el(field).value=value[field];
    if(['segments','hours','alpha_asc','alpha_desc'].includes(value.sort))el('filterSort').value=value.sort;
    if(['compact','comfortable'].includes(value.density)){el('density').value=value.density;document.body.classList.toggle('compact',value.density==='compact')}
    el('identityBasis').value=value.identity_basis==='cli_ip'?'cli_ip':'device_id';renderFilters();apply();
}
window.restoreSharedView=()=>{
    el('qualitySummary').textContent=`Title labels are log-derived; conflicting or unverified names remain flagged. Snapshot built ${meta.built_at.slice(0,16).replace('T',' ')}.`;
    if(!location.hash.startsWith('#view='))return false;
    try{restore(JSON.parse(decodeURIComponent(location.hash.slice(6))));message('Shared view loaded');return true}catch(e){message(e.message);return false}
};
function currentView(){if(!applied)throw Error('Apply filters first');return {...applied,sort:el('filterSort').value,density:el('density').value}}
el('saveView').onclick=()=>{try{const name=el('savedName').value.trim();if(!name||name.length>100)throw Error('Enter a view name (1–100 characters)');const saved=views();Object.defineProperty(saved,name,{value:currentView(),enumerable:true,configurable:true,writable:true});localStorage.setItem(key,JSON.stringify(saved));list();message('Applied filters saved on this browser')}catch(e){message(e.message)}};
el('loadView').onclick=()=>{try{const saved=views(),name=el('savedName').value;if(!Object.hasOwn(saved,name))throw Error('Choose an existing saved view');restore(saved[name]);message('Saved view loaded')}catch(e){message(e.message)}};
el('deleteView').onclick=()=>{try{const saved=views();delete saved[el('savedName').value];localStorage.setItem(key,JSON.stringify(saved));list();message('Saved view deleted')}catch(e){message(e.message)}};
el('shareView').onclick=async()=>{try{const url=new URL(location.href);url.hash='view='+encodeURIComponent(JSON.stringify(currentView()));history.replaceState(null,'',url);await navigator.clipboard.writeText(url.href);message('Local view link copied; opens on this machine')}catch(e){message('Copy the view link from the address bar. It includes the applied filter values.')}};
window.renderDevices=(devices,basis)=>{el('explorerLabel').textContent=basis==='cli_ip'?'Client IP explorer':'Device explorer';const root=el('deviceExplorer');root.replaceChildren();if(!devices.length){root.textContent='No known identifiers in this selection.';return}for(const d of devices){const b=document.createElement('button');b.className='device-card';const title=document.createElement('b');title.textContent=d.identity_value;const info=document.createElement('span');info.textContent=`${Number(d.hours).toFixed(2)} estimated h · ${d.videos} video keys`;const note=document.createElement('small');note.textContent=(basis==='cli_ip'?'Shared-address activity':d.confidence)+' · Open journey →';b.append(title,info,note);b.onclick=async()=>{draft[basis]=new Set([d.identity_value]);renderFilters();await apply();document.querySelector('.journey-panel').scrollIntoView({behavior:'smooth',block:'start'})};root.append(b)}};
el('journeyExport').onclick=async()=>{const button=el('journeyExport');button.disabled=true;try{if(!applied)throw Error('Apply an identifier first');const response=await request('/api/journey-export',applied);const url=URL.createObjectURL(await response.blob()),a=document.createElement('a');a.href=url;a.download='smartvod_viewer_journey.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}catch(e){el('journeyStatus').textContent=e.message}finally{button.disabled=false}};
list();
})();

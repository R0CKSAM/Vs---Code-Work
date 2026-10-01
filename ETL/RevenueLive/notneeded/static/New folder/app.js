'use strict';
const $=id=>document.getElementById(id);
document.querySelector('#shell > header').append($('revenueHeader'));
const topHeader=document.querySelector('#shell > header');
const headerRow=document.createElement('div');headerRow.className='header-row';
headerRow.append(topHeader.querySelector('.wordmark'),document.querySelector('#shell > nav'),topHeader.querySelector('.identity'));
topHeader.prepend(headerRow);
$('revenueHeader').append($('export'));
function positionChannelMenu(){
  if(!$('channelPicker').open)return;
  const rect=$('channelPicker').getBoundingClientRect(),menu=$('channelPicker').querySelector('.channel-menu');
  const width=Math.min(320,innerWidth-24);
  menu.style.width=width+'px';menu.style.left=Math.max(12,Math.min(rect.left,innerWidth-width-12))+'px';
  menu.style.top=Math.min(rect.bottom+5,innerHeight-100)+'px';menu.style.maxHeight=Math.max(80,innerHeight-rect.bottom-17)+'px';
}
$('channelPicker').addEventListener('toggle',positionChannelMenu);
window.addEventListener('resize',positionChannelMenu);
document.addEventListener('scroll',positionChannelMenu,true);
new MutationObserver(()=>{$('revenueHeader').hidden=$('dashboard').hidden;}).observe($('dashboard'),{attributes:true,attributeFilter:['hidden']});
let me=null,csrf='',pending=null,users=[],adminChannels=[];
let selectedChannels=new Set(),reportRows=[],appliedQuery='',pageIndex=0,latestDay='',requestNumber=0;
let accessEpoch=0,checkingAccess=false;
let filterTimer;
const availableDates=document.createElement('datalist');availableDates.id='availableDates';document.body.append(availableDates);
for(const id of ['start','end'])$(id).removeAttribute('list');
const dateCoverage=document.createElement('span');dateCoverage.id='dateCoverage';$('filterState').before(dateCoverage);
$('filters').querySelector('button.primary').hidden=true;
document.querySelector('#trendChart').closest('.chart-block').querySelector('.chart-heading').append(document.querySelector('.chart-controls'));
$('datePreset').closest('label').hidden=true;
$('revenueHeader').querySelector('.section-title').hidden=true;
const accountMenu=document.createElement('details');accountMenu.id='accountMenu';
const menuTitle=document.createElement('summary');menuTitle.textContent='Menu';accountMenu.append(menuTitle);
const menuPanel=document.createElement('div');menuPanel.className='account-panel';
menuPanel.append(headerRow.querySelector('nav'),headerRow.querySelector('.identity'));accountMenu.append(menuPanel);
topHeader.prepend(accountMenu);
menuPanel.prepend($('export'));
menuPanel.querySelector('.currency')?.remove();
headerRow.remove();
document.addEventListener('click',e=>{if(!accountMenu.contains(e.target))accountMenu.open=false;});
menuPanel.querySelectorAll('[data-view]').forEach(button=>button.addEventListener('click',()=>{accountMenu.open=false;}));
const loading=document.createElement('div');loading.id='reportLoading';loading.hidden=true;loading.setAttribute('role','status');loading.innerHTML='<span class="loading-spinner" aria-hidden="true"></span><span>Updating data...</span>';document.body.append(loading);
let loadingTicket=0;
function setLoading(value){loading.hidden=!value;$('dashboard').setAttribute('aria-busy',String(value));}
const money=n=>new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR'}).format(n/100);
const number=n=>new Intl.NumberFormat('en-IN').format(n);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function notify(message){$('notice').textContent=message;$('notice').hidden=false;}
async function api(path,options={}){
  const epoch=accessEpoch;
  const headers={'X-CSRF-Token':csrf,...options.headers};
  if(options.body && !(options.body instanceof FormData)){headers['Content-Type']='application/json';options.body=JSON.stringify(options.body);}
  const response=await fetch(path,{...options,headers});
  const data=await response.json();
  if(epoch!==accessEpoch){const error=new Error('Access changed; stale response discarded.');error.stale=true;throw error;}
  if(!response.ok){if(response.status===401)signOutView('Session ended. Sign in again.');const error=new Error(data.error||'Request failed.');error.status=response.status;throw error;}
  return data;
}
function bind(id,event,fn){$(id).addEventListener(event,async e=>{e.preventDefault();const button=e.submitter||((e.target.tagName==='BUTTON')?e.target:null);if(button)button.disabled=true;try{await fn(e);}catch(error){if(!error.stale){const dialog=e.target.closest('dialog');if(dialog?.open&&dialog.querySelector('.form-error'))dialog.querySelector('.form-error').textContent=error.message;else if(me)notify(error.message);else $('loginError').textContent=error.message;}}finally{if(button)button.disabled=false;}});}
function clearSensitive(){
  loadingTicket++;setLoading(false);
  clearTimeout(filterTimer);availableDates.replaceChildren();dateCoverage.textContent='';
  accessEpoch++;requestNumber++;reportRows=[];users=[];adminChannels=[];pending=null;appliedQuery='';latestDay='';pageIndex=0;
  for(const dialog of document.querySelectorAll('dialog[open]'))dialog.close();
  for(const id of ['records','history','users','channelDirectory','previewRows','assignments','channelOptions'])$(id).replaceChildren();
  for(const id of ['total','ad','other','views','impressions','rowCount','period','pageInfo','appliedScope'])$(id).textContent='-';
  $('dataSignal').textContent='';$('revenueMix').hidden=true;
  $('preview').hidden=true;$('export').disabled=true;$('userForm').reset();$('passwordForm').reset();$('uploadForm').reset();
  if(window.RevenueCharts)RevenueCharts.render([]);
}
function signOutView(message){clearSensitive();me=null;csrf='';selectedChannels.clear();$('shell').hidden=true;$('login').hidden=false;$('loginError').textContent=message;}
function identity(value){
  me=value;csrf=value.csrf;$('login').hidden=true;$('shell').hidden=false;
  $('identity').textContent=value.user.username+' | '+(value.user.super_admin?'Super Admin':value.user.role);
  $('uploadNav').hidden=value.user.role==='viewer';$('adminNav').hidden=value.user.role!=='admin';$('demoBanner').hidden=!value.demo;
}
function overview(){document.querySelectorAll('.view').forEach(v=>v.hidden=v.id!=='dashboard');document.querySelectorAll('[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view==='dashboard'));}
function passwordPrompt(){
  const first=!!me.user.must_change;
  $('passwordTitle').textContent=first?'Set your own password':'Change password';
  $('currentPasswordLabel').textContent=first?'Temporary password':'Current password';
  $('passwordCancel').hidden=first;$('passwordDialog').querySelector('.form-error').textContent='';
  if(!$('passwordDialog').open)$('passwordDialog').showModal();
}
function accessSignature(value){return JSON.stringify([value.user.id,value.user.username,value.user.role,value.user.super_admin,value.user.must_change,value.channels]);}
async function session(){
  const value=await api('/api/me');clearSensitive();identity(value);overview();
  selectedChannels=new Set(value.channels.map(c=>String(c.id)));renderChannelOptions();
  if(value.user.must_change){passwordPrompt();return;}
  $('passwordCancel').hidden=false;await refresh();
}
async function syncAccess(){
  if(!me||checkingAccess)return;
  checkingAccess=true;
  try{
    const value=await api('/api/me');
    if(!me||accessSignature(value)===accessSignature(me))return;
    const params=new URLSearchParams(appliedQuery),oldIds=new Set(params.getAll('channel'));
    const wasAll=me.channels.length===0||(!!appliedQuery&&me.channels.every(c=>oldIds.has(String(c.id)))&&oldIds.size===me.channels.length);
    const next=new Set(value.channels.map(c=>String(c.id)));
    const selection=wasAll?next:new Set([...oldIds].filter(id=>next.has(id)));
    clearSensitive();identity(value);overview();selectedChannels=selection;renderChannelOptions();
    if(params.has('start'))$('start').value=params.get('start');if(params.has('end'))$('end').value=params.get('end');
    if(value.user.must_change){passwordPrompt();return;}
    await refresh();notify('Your access was updated. Current permissions are now applied.');
  }catch(error){if(!error.stale&&error.status!==401&&me)signOutView('Connection or access check failed. Sign in again to verify access.');}
  finally{checkingAccess=false;}
}
function renderChannelOptions(){
  $('channelOptions').innerHTML=me.channels.map(c=>`<label><input type="checkbox" value="${c.id}" ${selectedChannels.has(String(c.id))?'checked':''}>${esc(c.name)}</label>`).join('');
  filterChannelOptions();channelSummary();
}
function channelSummary(){
  const size=selectedChannels.size;
  $('channelSummary').textContent=size===0?'No channels selected':size===me.channels.length?'All assigned channels ('+size+')':size===1?me.channels.find(c=>selectedChannels.has(String(c.id))).name:size+' channels selected';
}
function filterChannelOptions(){const text=$('channelSearch').value.trim().toLowerCase();for(const label of $('channelOptions').children)label.hidden=!label.textContent.toLowerCase().includes(text);}
function dirty(){
  clearTimeout(filterTimer);requestNumber++;$('export').disabled=true;
  $('filterState').textContent='Updating...';
  filterTimer=setTimeout(()=>{if(!me)return;if($('start').value&&$('end').value&&$('start').value>$('end').value){$('filterState').textContent='Choose an end date on or after the start date';return;}refresh().catch(error=>{if(!error.stale)notify(error.message);});},300);
}
function query(){const params=new URLSearchParams({start:$('start').value,end:$('end').value});if(!selectedChannels.size)params.append('channel','none');else for(const id of [...selectedChannels].sort((a,b)=>Number(a)-Number(b)))params.append('channel',id);return params.toString();}
function renderTable(){const size=Number($('pageSize').value),pages=Math.max(1,Math.ceil(reportRows.length/size));pageIndex=Math.min(pageIndex,pages-1);const subset=reportRows.slice(pageIndex*size,(pageIndex+1)*size);
  $('records').innerHTML=subset.map(r=>`<tr${r.total===0?' class="zero-row"':''}><td>${esc(r.day)}</td><td>${esc(r.channel)}</td><td class="number">${number(r.views)}</td><td class="number">${number(r.impressions)}</td><td class="number">${money(r.ad)}</td><td class="number">${money(r.other)}</td><td class="number"><strong>${money(r.total)}</strong></td></tr>`).join('');
  $('pageInfo').textContent=reportRows.length?`${pageIndex*size+1}-${Math.min((pageIndex+1)*size,reportRows.length)} of ${number(reportRows.length)}`:'0 records';$('previousPage').disabled=pageIndex===0;$('nextPage').disabled=pageIndex>=pages-1;
}
async function refresh(){
  const ticket=++loadingTicket;setLoading(true);
  try{return await loadReport();}finally{if(ticket===loadingTicket)setLoading(false);}
}
async function loadReport(){
  clearTimeout(filterTimer);
  const sequence=++requestNumber,requested=query(),scope=$('channelSummary').textContent;
  $('filterState').textContent='Loading...';$('export').disabled=true;
  let data;try{data=await api('/api/report?'+requested);}catch(error){if(error.stale)return;if(sequence===requestNumber){$('filterState').textContent='Could not apply filters';$('export').disabled=!appliedQuery;}throw error;}
  if(sequence!==requestNumber)return;
  appliedQuery=requested;reportRows=data.rows;pageIndex=0;
  const dates=data.available_dates||[];
  availableDates.replaceChildren(...dates.map(day=>{const option=document.createElement('option');option.value=day;return option;}));
  for(const id of ['start','end']){if(dates.length){$(id).min=dates[0];$(id).max=dates[dates.length-1];}else{$(id).removeAttribute('min');$(id).removeAttribute('max');}}
  latestDay=dates.at(-1)||'';
  dateCoverage.textContent=dates.length?'Available data: '+dates[0]+' to '+dates.at(-1)+' ('+dates.length+' days)':'No data for selected channels';
  if(data.rows.length)latestDay=data.rows.reduce((last,r)=>r.day>last?r.day:last,latestDay);
  for(const k of ['total','ad','other'])$(k).textContent=money(data.totals[k]);
  $('views').textContent=number(data.totals.views);$('impressions').textContent=number(data.totals.impressions)+' ad impressions';
  const adShare=data.totals.total?Math.round(data.totals.ad/data.totals.total*100):0,otherShare=data.totals.total?100-adShare:0;
  $('revenueMixAd').style.width=adShare+'%';$('revenueMixOther').style.width=otherShare+'%';
  $('revenueMix').setAttribute('aria-label','Ad revenue '+adShare+'%, sponsorship and other '+otherShare+'%');
  $('revenueMix').hidden=!data.totals.total;
  const channelTotals=new Map();for(const r of data.rows)channelTotals.set(r.channel,(channelTotals.get(r.channel)||0)+r.total);
  const active=[...channelTotals.values()].filter(v=>v>0).length,tracked=channelTotals.size;
  $('dataSignal').textContent=tracked?active+' of '+tracked+' channels earned revenue in this period.'+(data.totals.other===0&&data.totals.total>0?' All revenue is from ads — no sponsorship recorded.':''):'';
  renderTable();
  try{RevenueCharts.render(data.rows);}catch(error){notify('Charts could not render. The table and CSV export remain available.');}
  $('rowCount').textContent=number(data.rows.length)+' records';$('empty').hidden=data.rows.length>0;
  $('period').textContent=data.rows.length?[...new Set(data.rows.map(r=>r.day))].sort().filter((v,i,a)=>i===0||i===a.length-1).join(' to '):'No data';
  const params=new URLSearchParams(requested);$('appliedScope').textContent=scope+' | '+(params.get('start')||'Beginning')+' to '+(params.get('end')||'Latest');
  $('filterState').textContent=query()===requested?'Updated':'Updating...';$('export').disabled=false;
  $('updated').textContent='Updated '+new Date().toLocaleTimeString('en-IN');
}
bind('loginForm','submit',async()=>{
  const values=Object.fromEntries(new FormData($('loginForm')));
  try{await api('/api/login',{method:'POST',body:values});$('loginError').textContent='';$('loginForm').reset();await session();}catch(error){if(!error.stale){if(me)notify(error.message);else $('loginError').textContent=error.message;}}
});
bind('logout','click',async()=>{await api('/api/logout',{method:'POST'});location.reload();});
bind('filters','submit',refresh);
bind('reset','click',async()=>{HTMLFormElement.prototype.reset.call($('filters'));$('channelSearch').value='';$('end').disabled=false;selectedChannels=new Set(me.channels.map(c=>String(c.id)));renderChannelOptions();await refresh();});
bind('export','click',async()=>{window.location.href='/api/export?'+appliedQuery;});
$('channelSearch').addEventListener('input',filterChannelOptions);
const selectAllChannels=document.createElement('button');
selectAllChannels.type='button';selectAllChannels.id='selectAllChannels';selectAllChannels.textContent='Select all';
$('selectVisible').before(selectAllChannels);
bind('selectAllChannels','click',async()=>{selectedChannels=new Set(me.channels.map(c=>String(c.id)));renderChannelOptions();dirty();});
$('channelOptions').addEventListener('change',e=>{if(e.target.checked)selectedChannels.add(e.target.value);else selectedChannels.delete(e.target.value);channelSummary();dirty();});
bind('selectVisible','click',async()=>{for(const label of $('channelOptions').children)if(!label.hidden){const input=label.querySelector('input');selectedChannels.add(input.value);input.checked=true;}channelSummary();dirty();});
bind('clearChannels','click',async()=>{selectedChannels.clear();for(const input of $('channelOptions').querySelectorAll('input'))input.checked=false;channelSummary();dirty();});
document.addEventListener('click',e=>{if(!$('channelPicker').contains(e.target))$('channelPicker').open=false;});
document.addEventListener('keydown',e=>{if(e.key==='Escape')$('channelPicker').open=false;});
for(const id of ['start','end'])$(id).addEventListener('change',()=>{if($('datePreset').value==='single')$('end').value=$('start').value;else $('datePreset').value='custom';dirty();});
$('datePreset').addEventListener('change',()=>{
  const value=$('datePreset').value,anchor=latestDay||new Date().toISOString().slice(0,10);$('end').disabled=value==='single';
  if(value==='all'){$('start').value='';$('end').value='';}
  else if(value==='single'){$('start').value=$('start').value||anchor;$('end').value=$('start').value;}
  else if(value==='month'){$('start').value=anchor.slice(0,7)+'-01';$('end').value=anchor;}
  else if(value==='7'||value==='30'){const date=new Date(anchor+'T00:00:00Z');date.setUTCDate(date.getUTCDate()-Number(value)+1);$('start').value=date.toISOString().slice(0,10);$('end').value=anchor;}
  dirty();
});
$('pageSize').addEventListener('change',()=>{pageIndex=0;renderTable();});
// Pagination owns its disabled state after rendering.
$('previousPage').addEventListener('click',()=>{pageIndex--;renderTable();});
$('nextPage').addEventListener('click',()=>{pageIndex++;renderTable();});
bind('passwordButton','click',async()=>{$('passwordForm').reset();passwordPrompt();});
bind('passwordSignout','click',async()=>{await api('/api/logout',{method:'POST'});signOutView('Signed out.');});
bind('passwordCancel','click',async()=>{$('passwordDialog').close();});
$('passwordDialog').addEventListener('cancel',e=>{if(me?.user.must_change)e.preventDefault();});
bind('passwordForm','submit',async()=>{const body=Object.fromEntries(new FormData($('passwordForm')));if(body.password!==body.confirm)throw new Error('The new passwords do not match.');await api('/api/password',{method:'POST',body});$('passwordDialog').close();$('passwordForm').reset();await session();notify('Password updated.');});
for(const button of document.querySelectorAll('[data-view]'))button.addEventListener('click',async()=>{
  try{document.querySelectorAll('.view').forEach(v=>v.hidden=v.id!==button.dataset.view);document.querySelectorAll('[data-view]').forEach(b=>b.classList.toggle('active',b===button));$('notice').hidden=true;if(button.dataset.view==='uploads')await history();if(button.dataset.view==='admin')await loadUsers();if(button.dataset.view==='dashboard')await refresh();}catch(e){notify(e.message);}
});
bind('uploadForm','submit',async()=>{
  pending=await api('/api/uploads/preview',{method:'POST',body:new FormData($('uploadForm'))});
  $('preview').hidden=false;$('replace').checked=false;$('replaceLabel').hidden=pending.duplicates===0;
  $('previewCount').textContent=number(pending.rows.length)+' rows | '+pending.duplicates+' replacements';
  $('previewRows').innerHTML=pending.rows.slice(0,200).map(r=>`<tr><td>${esc(r.day)}</td><td>${esc(r.channel)}</td><td class="number">${number(r.views)}</td><td class="number">${money(r.total)}</td></tr>`).join('');
  if(pending.rows.length>200)notify('Preview shows the first 200 rows. All '+pending.rows.length+' rows were validated.');
});
bind('cancelUpload','click',async()=>{pending=null;$('preview').hidden=true;$('uploadForm').reset();});
bind('publish','click',async()=>{
  if(!pending)return;if(pending.duplicates&&!$('replace').checked)throw new Error('Confirm replacement before publishing.');
  if(!confirm('Publish '+pending.rows.length+' revenue records'+(pending.duplicates?' and replace '+pending.duplicates+' existing records':'')+'?'))return;
  await api('/api/uploads/'+pending.id+'/commit',{method:'POST',body:{replace:$('replace').checked}});
  pending=null;$('preview').hidden=true;$('uploadForm').reset();notify('Data published.');await history();
});
const history=async()=>{const data=await api('/api/uploads');$('history').innerHTML=data.rows.map(r=>`<tr><td>${esc(new Date(r.created).toLocaleString('en-IN'))}</td><td>${esc(r.filename)}</td><td>${esc(r.username)}</td><td><span class="badge">${esc(r.state)}</span></td><td>${me.user.role==='admin'&&r.state==='committed'?`<button data-restore="${esc(r.id)}">Roll back</button>`:''}</td></tr>`).join('');};
$('history').addEventListener('click',async e=>{const button=e.target.closest('[data-restore]');if(!button||!confirm('Restore the previous data for this upload?'))return;button.disabled=true;try{await api('/api/uploads/'+button.dataset.restore+'/restore',{method:'POST'});await history();notify('Previous data restored.');}catch(error){notify(error.message);}finally{button.disabled=false;}});
async function loadUsers(){
  const data=await api('/api/admin/users');users=data.users;adminChannels=data.channels;
  const active=new Set(adminChannels.map(c=>c.id));
  const scope=u=>{const count=u.channels.filter(id=>active.has(id)).length;return u.role==='admin'?'All channels':count===0?'No channels':count===active.size?'All assigned channels ('+count+')':count+' of '+active.size+' channels';};
  $('users').innerHTML=users.map(u=>`<tr><td>${esc(u.username)}</td><td>${u.super_admin?'Super Admin':esc(u.role)}</td><td>${scope(u)}</td><td>${!u.active?'Disabled':u.must_change?'Password setup pending':'Enabled'}</td><td>${u.super_admin||(!me.user.super_admin&&u.role==='admin')?'Protected':`<button data-user="${u.id}">Edit</button>`}</td></tr>`).join('');
  $('userForm').elements.role.querySelector('option[value="admin"]').disabled=!me.user.super_admin;
  $('channelDirectory').innerHTML=[...data.channels.map(c=>({...c,archived:false})),...(data.archived||[]).map(c=>({...c,archived:true}))].map(c=>`<div><span>${esc(c.name)}${c.archived?' (archived)':''}</span> <button type="button" data-channel="${c.id}" data-archived="${!c.archived}">${c.archived?'Restore':'Remove'}</button></div>`).join('');
}
$('channelDirectory').addEventListener('click',async e=>{
  const button=e.target.closest('[data-channel]');if(!button)return;
  const archived=button.dataset.archived==='true';
  if(!confirm(archived?'Remove this channel from active reports, uploads and user selections? Saved revenue is retained; Restore brings it back.':'Restore this channel and its retained user assignments?'))return;
  button.disabled=true;
  try{await api('/api/admin/channels/'+button.dataset.channel+'/archive',{method:'POST',body:{archived}});await syncAccess();if(me?.user.role==='admin')await loadUsers();notify(archived?'Channel archived. Saved revenue retained.':'Channel restored.');}catch(error){if(!error.stale)notify(error.message);}finally{button.disabled=false;}
});
function assignmentSummary(){
  const labels=[...$('assignments').children],shown=labels.filter(label=>!label.hidden).length,selected=$('assignments').querySelectorAll('input:checked').length;
  $('assignmentCount').textContent=selected+' selected | '+shown+' shown | '+labels.length+' total';
}
function assignmentRole(){const admin=$('userForm').elements.role.value==='admin';$('assignmentFieldset').dataset.admin=String(admin);$('adminAccessNote').hidden=!admin;}
function editUser(user){const form=$('userForm');form.reset();form.elements.id.value=user?.id||'';form.elements.username.value=user?.username||'';form.elements.role.value=user?.role||'viewer';form.elements.active.checked=user?!!user.active:true;form.elements.password.required=!user;form.elements.password.type='password';$('temporaryPasswordLabel').textContent=user?'Reset password (optional, 12+ characters)':'Temporary password (12+ characters)';$('userTitle').textContent=user?'Edit user':'Add user';$('userDialog').querySelector('.form-error').textContent='';$('assignmentSearch').value='';$('assignments').innerHTML=adminChannels.map(c=>`<label class="check"><input type="checkbox" value="${c.id}" ${user?.channels.includes(c.id)?'checked':''}>${esc(c.name)}</label>`).join('');assignmentSummary();assignmentRole();$('userDialog').showModal();}
bind('addUser','click',async()=>editUser());
$('users').addEventListener('click',e=>{const button=e.target.closest('[data-user]');if(button)editUser(users.find(u=>u.id===Number(button.dataset.user)));});
bind('userCancel','click',async()=>$('userDialog').close());
$('assignmentSearch').addEventListener('input',()=>{const search=$('assignmentSearch').value.trim().toLowerCase();for(const label of $('assignments').children)label.hidden=!label.textContent.toLowerCase().includes(search);assignmentSummary();});
$('assignments').addEventListener('change',assignmentSummary);
$('userForm').elements.role.addEventListener('change',assignmentRole);
$('showTemporary').addEventListener('change',()=>{$('userForm').elements.password.type=$('showTemporary').checked?'text':'password';});
for(const [id,mode] of [['assignAll','all'],['assignShown','shown'],['assignClear','clear']])bind(id,'click',async()=>{for(const label of $('assignments').children)if(mode!=='shown'||!label.hidden)label.querySelector('input').checked=mode!=='clear';assignmentSummary();});
bind('userForm','submit',async()=>{const form=$('userForm');const body={invite:$('inviteEmail').checked,id:form.elements.id.value?Number(form.elements.id.value):null,username:form.elements.username.value,role:form.elements.role.value,password:form.elements.password.value,active:form.elements.active.checked,channels:form.elements.role.value==='admin'?[]:[...$('assignments').querySelectorAll('input:checked')].map(c=>Number(c.value))};await api('/api/admin/users',{method:'POST',body});$('userDialog').close();form.reset();await loadUsers();notify(body.invite?'Invitation sent. User will set their own password.':body.id?'User access saved. Open clients update automatically.':'User created: '+body.username.trim()+'. Sign-in address: '+location.origin+'/');});
bind('channelForm','submit',async()=>{await api('/api/admin/channels',{method:'POST',body:Object.fromEntries(new FormData($('channelForm')))});$('channelForm').reset();await loadUsers();notify('Channel added.');});
const inviteLabel=document.createElement('label');inviteLabel.className='check';
inviteLabel.innerHTML='<input type="checkbox" id="inviteEmail">Invite by email';
$('userForm').elements.username.closest('label').after(inviteLabel);
function inviteMode(){const form=$('userForm'),editing=!!form.elements.id.value;inviteLabel.hidden=editing;if(editing)$('inviteEmail').checked=false;const enabled=$('inviteEmail').checked;form.elements.password.required=!editing&&!enabled;form.elements.password.closest('label').hidden=enabled;form.elements.username.type=enabled?'email':'text';$('showTemporary').closest('label').hidden=enabled;}
$('inviteEmail').addEventListener('change',inviteMode);
new MutationObserver(inviteMode).observe($('userDialog'),{attributes:true,attributeFilter:['open']});
const resetDialog=document.createElement('dialog');resetDialog.id='accountDialog';
resetDialog.innerHTML='<form id="accountForm"><h2 id="accountTitle">Forgot password</h2><label id="accountEmailLabel">Email<input name="email" type="email" required autocomplete="email"></label><label id="accountPasswordLabel" hidden>New password<input name="password" type="password" minlength="12" maxlength="256" autocomplete="new-password"></label><label id="accountConfirmLabel" hidden>Confirm password<input name="confirm" type="password" autocomplete="new-password"></label><p class="form-error" role="alert"></p><div class="actions"><button class="primary">Continue</button><button type="button" id="accountCancel">Cancel</button></div></form>';
document.body.append(resetDialog);
const forgot=document.createElement('button');forgot.type='button';forgot.textContent='Forgot password';$('loginForm').append(forgot);
let accountToken=new URLSearchParams(location.hash.slice(1)).get('account-token')||'';
if(accountToken)window.history.replaceState(null,'',location.pathname+location.search);
function openAccount(){const form=$('accountForm');form.reset();$('accountTitle').textContent=accountToken?'Set your password':'Forgot password';$('accountEmailLabel').hidden=!!accountToken;$('accountPasswordLabel').hidden=!accountToken;$('accountConfirmLabel').hidden=!accountToken;form.elements.email.required=!accountToken;form.elements.password.required=!!accountToken;form.elements.confirm.required=!!accountToken;resetDialog.querySelector('.form-error').textContent='';resetDialog.showModal();}
forgot.addEventListener('click',()=>{accountToken='';openAccount();});
bind('accountCancel','click',async()=>{accountToken='';resetDialog.close();});
bind('accountForm','submit',async()=>{const form=$('accountForm');if(accountToken&&form.elements.password.value!==form.elements.confirm.value)throw new Error('Passwords do not match.');const result=await api(accountToken?'/api/account/complete':'/api/account/request',{method:'POST',body:accountToken?{token:accountToken,password:form.elements.password.value}:{email:form.elements.email.value}});const completed=!!accountToken;accountToken='';resetDialog.close();if(completed)signOutView('Password saved. Sign in with your email and new password.');else if(me)notify(result.message);else $('loginError').textContent=result.message;});
session().catch(()=>{$('login').hidden=false;$('shell').hidden=true;}).finally(()=>{if(accountToken)openAccount();});
setInterval(syncAccess,2000);
window.addEventListener('focus',syncAccess);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)syncAccess();});
window.addEventListener('offline',()=>{if(me)signOutView('Connection lost. Sign in again when connected.');});

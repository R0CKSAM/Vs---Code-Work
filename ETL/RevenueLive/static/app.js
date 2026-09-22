'use strict';
const $=id=>document.getElementById(id);
let me=null,csrf='',pending=null,users=[];
let selectedChannels=new Set(),reportRows=[],appliedQuery='',pageIndex=0,latestDay='',requestNumber=0;
const money=n=>new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR'}).format(n/100);
const number=n=>new Intl.NumberFormat('en-IN').format(n);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function notify(message){$('notice').textContent=message;$('notice').hidden=false;}
async function api(path,options={}){
  const headers={'X-CSRF-Token':csrf,...options.headers};
  if(options.body && !(options.body instanceof FormData)){headers['Content-Type']='application/json';options.body=JSON.stringify(options.body);}
  const response=await fetch(path,{...options,headers});
  const data=await response.json();
  if(!response.ok){if(response.status===401){$('shell').hidden=true;$('login').hidden=false;}throw new Error(data.error||'Request failed.');}
  return data;
}
function bind(id,event,fn){$(id).addEventListener(event,async e=>{e.preventDefault();const button=e.submitter||((e.target.tagName==='BUTTON')?e.target:null);if(button)button.disabled=true;try{await fn(e);}catch(error){const dialog=e.target.closest('dialog');if(dialog)dialog.querySelector('.form-error').textContent=error.message;else notify(error.message);}finally{if(button)button.disabled=false;}});}
async function session(){
  const value=await api('/api/me');me=value;csrf=value.csrf;
  $('login').hidden=true;$('shell').hidden=false;$('identity').textContent=value.user.username+' | '+value.user.role;
  $('uploadNav').hidden=value.user.role==='viewer';$('adminNav').hidden=value.user.role!=='admin';
  $('demoBanner').hidden=!value.demo;
  selectedChannels=new Set(value.channels.map(c=>String(c.id)));renderChannelOptions();
  if(value.user.must_change){$('passwordCancel').hidden=true;$('passwordDialog').showModal();return;}
  $('passwordCancel').hidden=false;await refresh();
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
function dirty(){$('filterState').textContent='Unapplied changes';}
function query(){const params=new URLSearchParams({start:$('start').value,end:$('end').value});if(!selectedChannels.size)params.append('channel','none');else for(const id of [...selectedChannels].sort((a,b)=>Number(a)-Number(b)))params.append('channel',id);return params.toString();}
function renderTable(){const size=Number($('pageSize').value),pages=Math.max(1,Math.ceil(reportRows.length/size));pageIndex=Math.min(pageIndex,pages-1);const subset=reportRows.slice(pageIndex*size,(pageIndex+1)*size);
  $('records').innerHTML=subset.map(r=>`<tr><td>${esc(r.day)}</td><td>${esc(r.channel)}</td><td class="number">${number(r.views)}</td><td class="number">${number(r.impressions)}</td><td class="number">${money(r.ad)}</td><td class="number">${money(r.other)}</td><td class="number"><strong>${money(r.total)}</strong></td></tr>`).join('');
  $('pageInfo').textContent=reportRows.length?`${pageIndex*size+1}-${Math.min((pageIndex+1)*size,reportRows.length)} of ${number(reportRows.length)}`:'0 records';$('previousPage').disabled=pageIndex===0;$('nextPage').disabled=pageIndex>=pages-1;
}
async function refresh(){
  const sequence=++requestNumber,requested=query(),scope=$('channelSummary').textContent;
  $('filterState').textContent='Loading...';$('export').disabled=true;
  let data;try{data=await api('/api/report?'+requested);}catch(error){if(sequence===requestNumber){$('filterState').textContent='Could not apply filters';$('export').disabled=!appliedQuery;}throw error;}
  if(sequence!==requestNumber)return;
  appliedQuery=requested;reportRows=data.rows;pageIndex=0;
  if(data.rows.length)latestDay=data.rows.reduce((last,r)=>r.day>last?r.day:last,latestDay);
  for(const k of ['total','ad','other'])$(k).textContent=money(data.totals[k]);
  $('views').textContent=number(data.totals.views);$('impressions').textContent=number(data.totals.impressions)+' ad impressions';
  renderTable();
  try{RevenueCharts.render(data.rows);}catch(error){notify('Charts could not render. The table and CSV export remain available.');}
  $('rowCount').textContent=number(data.rows.length)+' records';$('empty').hidden=data.rows.length>0;
  $('period').textContent=data.rows.length?[...new Set(data.rows.map(r=>r.day))].sort().filter((v,i,a)=>i===0||i===a.length-1).join(' to '):'No data';
  const params=new URLSearchParams(requested);$('appliedScope').textContent=scope+' | '+(params.get('start')||'Beginning')+' to '+(params.get('end')||'Latest');
  $('filterState').textContent=query()===requested?'Filters applied':'Unapplied changes';$('export').disabled=false;$('channelPicker').open=false;
  $('updated').textContent='Updated '+new Date().toLocaleTimeString('en-IN');
}
bind('loginForm','submit',async()=>{
  const values=Object.fromEntries(new FormData($('loginForm')));
  try{await api('/api/login',{method:'POST',body:values});$('loginError').textContent='';$('loginForm').reset();await session();}catch(error){$('loginError').textContent=error.message;}
});
bind('logout','click',async()=>{await api('/api/logout',{method:'POST'});location.reload();});
bind('filters','submit',refresh);
bind('reset','click',async()=>{HTMLFormElement.prototype.reset.call($('filters'));$('end').disabled=false;selectedChannels=new Set(me.channels.map(c=>String(c.id)));renderChannelOptions();await refresh();});
bind('export','click',async()=>{window.location.href='/api/export?'+appliedQuery;});
$('channelSearch').addEventListener('input',filterChannelOptions);
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
bind('passwordButton','click',async()=>{$('passwordForm').reset();$('passwordDialog').querySelector('.form-error').textContent='';$('passwordDialog').showModal();});
bind('passwordCancel','click',async()=>{$('passwordDialog').close();});
$('passwordDialog').addEventListener('cancel',e=>{if(me?.user.must_change)e.preventDefault();});
bind('passwordForm','submit',async()=>{await api('/api/password',{method:'POST',body:Object.fromEntries(new FormData($('passwordForm')))});$('passwordDialog').close();$('passwordForm').reset();await session();notify('Password updated.');});
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
async function history(){const data=await api('/api/uploads');$('history').innerHTML=data.rows.map(r=>`<tr><td>${esc(new Date(r.created).toLocaleString('en-IN'))}</td><td>${esc(r.filename)}</td><td>${esc(r.username)}</td><td><span class="badge">${esc(r.state)}</span></td><td>${me.user.role==='admin'&&r.state==='committed'?`<button data-restore="${esc(r.id)}">Roll back</button>`:''}</td></tr>`).join('');}
$('history').addEventListener('click',async e=>{const button=e.target.closest('[data-restore]');if(!button||!confirm('Restore the previous data for this upload?'))return;button.disabled=true;try{await api('/api/uploads/'+button.dataset.restore+'/restore',{method:'POST'});await history();notify('Previous data restored.');}catch(error){notify(error.message);}finally{button.disabled=false;}});
async function loadUsers(){const data=await api('/api/admin/users');users=data.users;me.channels=data.channels;$('users').innerHTML=users.map(u=>`<tr><td>${esc(u.username)}</td><td>${esc(u.role)}</td><td>${u.role==='admin'?'All channels':u.channels.length+' assigned'}</td><td>${u.active?'Enabled':'Disabled'}</td><td><button data-user="${u.id}">Edit</button></td></tr>`).join('');$('channelDirectory').innerHTML=data.channels.map(c=>`<div>${esc(c.name)}</div>`).join('');}
function editUser(user){const form=$('userForm');form.reset();form.elements.id.value=user?.id||'';form.elements.username.value=user?.username||'';form.elements.role.value=user?.role||'viewer';form.elements.active.checked=user?!!user.active:true;form.elements.password.required=!user;$('userTitle').textContent=user?'Edit user':'Add user';$('userDialog').querySelector('.form-error').textContent='';$('assignmentSearch').value='';$('assignments').innerHTML=me.channels.map(c=>`<label class="check"><input type="checkbox" value="${c.id}" ${user?.channels.includes(c.id)?'checked':''}>${esc(c.name)}</label>`).join('');$('userDialog').showModal();}
bind('addUser','click',async()=>editUser());
$('users').addEventListener('click',e=>{const button=e.target.closest('[data-user]');if(button)editUser(users.find(u=>u.id===Number(button.dataset.user)));});
bind('userCancel','click',async()=>$('userDialog').close());
$('assignmentSearch').addEventListener('input',()=>{const search=$('assignmentSearch').value.toLowerCase();for(const label of $('assignments').children)label.hidden=!label.textContent.toLowerCase().includes(search);});
bind('userForm','submit',async()=>{const form=$('userForm');const body={id:form.elements.id.value?Number(form.elements.id.value):null,username:form.elements.username.value,role:form.elements.role.value,password:form.elements.password.value,active:form.elements.active.checked,channels:[...$('assignments').querySelectorAll('input:checked')].map(c=>Number(c.value))};await api('/api/admin/users',{method:'POST',body});$('userDialog').close();await loadUsers();notify('User access saved.');});
bind('channelForm','submit',async()=>{await api('/api/admin/channels',{method:'POST',body:Object.fromEntries(new FormData($('channelForm')))});$('channelForm').reset();await loadUsers();notify('Channel added.');});
session().catch(()=>{$('login').hidden=false;$('shell').hidden=true;});

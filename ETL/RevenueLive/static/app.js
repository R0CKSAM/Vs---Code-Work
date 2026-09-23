'use strict';
const themeStyle=document.createElement('link');themeStyle.rel='stylesheet';themeStyle.href='/static/dark.css';document.head.append(themeStyle);
const lightStyle=document.createElement('link');lightStyle.rel='stylesheet';lightStyle.href='/static/light.css';document.head.append(lightStyle);
const $=id=>document.getElementById(id);
const rankingScroll=document.createElement('div');rankingScroll.className='ranking-scroll';
$('rankFrame').before(rankingScroll);rankingScroll.append($('rankFrame'));
document.querySelector('#shell > header').append($('revenueHeader'));
const topHeader=document.querySelector('#shell > header');
const headerRow=document.createElement('div');headerRow.className='header-row';
headerRow.append(topHeader.querySelector('.wordmark'),document.querySelector('#shell > nav'),topHeader.querySelector('.identity'));
topHeader.prepend(headerRow);
$('revenueHeader').append($('export'));
function positionChannelMenu(){
  if(!$('channelPicker').open)return;
  const rect=$('channelPicker').getBoundingClientRect(),menu=$('channelPicker').querySelector('.channel-menu');
  const width=Math.min(rect.width,innerWidth-24);
  menu.style.width=width+'px';menu.style.left=Math.max(12,Math.min(rect.left,innerWidth-width-12))+'px';
  menu.style.top=Math.min(rect.bottom+5,innerHeight-100)+'px';menu.style.maxHeight=Math.max(80,innerHeight-rect.bottom-17)+'px';
}
$('channelPicker').addEventListener('toggle',positionChannelMenu);
$('channelPicker').addEventListener('toggle',()=>{if($('channelPicker').open)rangePicker.open=false;});
window.addEventListener('resize',positionChannelMenu);
document.addEventListener('scroll',positionChannelMenu,true);
const tabular=document.createElement('section');tabular.id='tabular';tabular.className='view';tabular.hidden=true;
const tableHeading=$('rowCount').closest('.section-title');
const tableWrap=$('records').closest('.table-wrap');
tabular.append(tableHeading,tableWrap,$('empty'),document.querySelector('.pagination'));
$('dashboard').after(tabular);
const tableNav=document.createElement('button');tableNav.dataset.view='tabular';tableNav.textContent='Tabular data';
document.querySelector('[data-view="dashboard"]').textContent='Dashboard';
document.querySelector('[data-view="dashboard"]').after(tableNav);
const diyView=document.createElement('section');diyView.id='diyGraphs';diyView.className='view';diyView.hidden=true;tabular.after(diyView);
const diyNav=document.createElement('button');diyNav.dataset.view='diyGraphs';diyNav.textContent='DIY - Graphs';tableNav.after(diyNav);
const insightsView=document.createElement('section');insightsView.id='insightsView';insightsView.className='view';insightsView.hidden=true;diyView.after(insightsView);
const insightsNav=document.createElement('button');insightsNav.dataset.view='insightsView';insightsNav.textContent='Quick Insights';document.querySelector('[data-view="dashboard"]').after(insightsNav);
const updateFilterVisibility=()=>{$('revenueHeader').hidden=$('dashboard').hidden&&tabular.hidden&&insightsView.hidden;};
for(const view of [$('dashboard'),tabular,diyView,insightsView])new MutationObserver(updateFilterVisibility).observe(view,{attributes:true,attributeFilter:['hidden']});
const diyScript=document.createElement('script');diyScript.src='/static/diy-graphs.js';document.head.append(diyScript);
let me=null,csrf='',pending=null,users=[],adminChannels=[];
let selectedChannels=new Set(),reportRows=[],appliedQuery='',pageIndex=0,latestDay='',requestNumber=0;
let accessEpoch=0,checkingAccess=false;
let filterTimer;
let initialWeek=true;
let resetDateBounds=false;
const signedInName=document.createElement('span');signedInName.id='signedInName';
document.querySelector('.metrics').innerHTML='<article><span>Total revenue</span><strong id="total">-</strong></article><article class="revenue-split"><div id="adMetric"><span>Ad revenue</span><strong id="ad">-</strong></div><div id="sponsorMetric"><span>Sponsorship / others</span><strong id="other">-</strong></div></article><article><span>Views</span><strong id="views">-</strong></article><article><span>Ad impressions</span><strong id="impressions">-</strong></article><span id="channelCount" hidden></span>';
document.querySelector('#trendChart').closest('.chart-block').querySelector('h3').textContent='Total revenue';
document.querySelectorAll('.metrics small:not(#impressions)').forEach(el=>el.remove());
const availableDates=document.createElement('datalist');availableDates.id='availableDates';document.body.append(availableDates);
for(const id of ['start','end'])$(id).removeAttribute('list');
const dateCoverage=document.createElement('span');dateCoverage.id='dateCoverage';$('filterState').before(dateCoverage);
$('filters').querySelector('button.primary').hidden=true;
$('reset').before($('interval').closest('label'));
$('interval').addEventListener('change',()=>{$('channelPicker').open=false;});
$('datePreset').closest('label').hidden=true;
$('revenueHeader').querySelector('.section-title').hidden=true;
const accountMenu=document.createElement('details');accountMenu.id='accountMenu';
const menuTitle=document.createElement('summary');menuTitle.append(signedInName);menuTitle.setAttribute('aria-label','Open account navigation');accountMenu.append(menuTitle);
const menuPanel=document.createElement('div');menuPanel.className='account-panel';
menuPanel.append(headerRow.querySelector('nav'),headerRow.querySelector('.identity'));accountMenu.append(menuPanel);
topHeader.prepend(accountMenu);
menuPanel.prepend($('export'));
const closeMenu=document.createElement('button');closeMenu.type='button';closeMenu.className='drawer-close';closeMenu.textContent='Close';closeMenu.addEventListener('click',()=>{accountMenu.open=false;menuTitle.focus();});menuPanel.prepend(closeMenu);
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&accountMenu.open){accountMenu.open=false;menuTitle.focus();}});
menuPanel.querySelector('.currency')?.remove();
headerRow.remove();
document.body.classList.add('summary-phase');
const rangePicker=document.createElement('details');rangePicker.id='rangePicker';
const rangeTitle=document.createElement('summary');rangeTitle.id='rangeTitle';rangeTitle.textContent='Latest week';rangePicker.append(rangeTitle);
const rangeText=document.createElement('span');rangeText.textContent='Latest week';rangeTitle.replaceChildren(rangeText);
const rangePanel=document.createElement('div');rangePanel.className='range-panel';rangePanel.append($('start').closest('label'),$('end').closest('label'));
rangePanel.querySelectorAll('label').forEach(label=>label.hidden=true);
let calendar=null,calendarDates=[];
const calendarInput=document.createElement('input');calendarInput.id='calendarInput';calendarInput.type='text';calendarInput.setAttribute('aria-label','Choose date or range');
const calendarHost=document.createElement('div');calendarHost.className='calendar-host';rangePanel.prepend(calendarHost);calendarHost.append(calendarInput);
const calendarNav=document.createElement('div');calendarNav.className='calendar-nav';calendarNav.innerHTML='<button type="button" aria-label="Previous month" title="Previous month">&#8249;</button><button type="button" id="chooseCalendarMonth"></button><button type="button" id="chooseCalendarYear"></button><button type="button" aria-label="Next month" title="Next month">&#8250;</button>';
const calendarChoices=document.createElement('div');calendarChoices.className='calendar-choices';calendarChoices.hidden=true;calendarHost.prepend(calendarNav,calendarChoices);
const navButtons=calendarNav.querySelectorAll('button');
function updateCalendarNav(){if(!calendar)return;navButtons[1].textContent=calendar.l10n.months.longhand[calendar.currentMonth];navButtons[2].textContent=String(calendar.currentYear);calendarChoices.hidden=true;}
navButtons[0].onclick=()=>{calendar.changeMonth(-1);updateCalendarNav();};navButtons[3].onclick=()=>{calendar.changeMonth(1);updateCalendarNav();};
function calendarOptions(years){if(!calendar)return;const values=years?[...new Set(calendarDates.map(day=>Number(day.slice(0,4))))]:Array.from({length:12},(_,i)=>i);calendarChoices.replaceChildren(...values.map(value=>{const button=document.createElement('button');button.type='button';button.textContent=years?String(value):calendar.l10n.months.shorthand[value];button.disabled=!years&&!calendarDates.some(day=>day.startsWith(calendar.currentYear+'-'+String(value+1).padStart(2,'0')));button.onclick=()=>{calendar.jumpToDate(new Date(years?value:calendar.currentYear,years?calendar.currentMonth:value,1));updateCalendarNav();};return button;}));calendarChoices.hidden=false;}
navButtons[1].onclick=()=>calendarOptions(false);navButtons[2].onclick=()=>calendarOptions(true);
const calendarStatus=document.createElement('p');calendarStatus.className='calendar-status sr-only';calendarStatus.setAttribute('role','status');rangePanel.append(calendarStatus);
let rangeStart=null;
function autoRange(dates,_,instance){if(!rangeStart){rangeStart=instance.latestSelectedDateObj||dates[0];if(rangeStart)instance.setDate([rangeStart],false);calendarStatus.textContent='Select the end date. Select the same date again for a single day.';return;}const end=dates.find(day=>day.getTime()!==rangeStart.getTime())||rangeStart;const days=[rangeStart,end].map(day=>instance.formatDate(day,'Y-m-d')).sort();$('start').value=days[0];$('end').value=days[1];$('datePreset').value='custom';rangeStart=null;rangePicker.open=false;dirty();}
function syncCalendar(){if(!calendar)return;rangeStart=null;calendar.set('monthSelectorType','static');calendar.set('enable',calendarDates);calendar.setDate([$('start').value,$('end').value].filter(Boolean),false);if($('end').value)calendar.jumpToDate($('end').value);updateCalendarNav();calendarStatus.textContent=calendarDates.length?'Select start and end dates.':'No dates available for the selected channels.';}
const calendarStyle=document.createElement('link');calendarStyle.rel='stylesheet';calendarStyle.href='/static/flatpickr.min.css';document.head.insertBefore(calendarStyle,themeStyle);
const calendarScript=document.createElement('script');calendarScript.src='/static/flatpickr.min.js';calendarScript.onload=()=>{calendar=flatpickr(calendarInput,{inline:true,mode:'multiple',dateFormat:'Y-m-d',disableMobile:true,enable:[],onChange:autoRange});syncCalendar();};document.head.append(calendarScript);
rangePicker.addEventListener('toggle',()=>{if(rangePicker.open){$('channelPicker').open=false;syncCalendar();}});
rangePicker.append(rangePanel);$('filters').prepend(rangePicker);$('revenueHeader').append($('export'));
function icon(name,className=''){const tile=document.createElement('span');tile.className=className;tile.setAttribute('aria-hidden','true');const glyph=document.createElement('i');glyph.dataset.lucide=name;tile.append(glyph);return tile;}
menuTitle.prepend(icon('chart-no-axes-combined','brand-icon'));
rangeTitle.prepend(icon('calendar-days'));
$('export').replaceChildren(icon('download'));$('export').title='Download CSV';$('export').setAttribute('aria-label','Download CSV');
document.querySelectorAll('.metrics article').forEach((card,index)=>card.prepend(icon(['indian-rupee','chart-pie','eye','megaphone'][index],'metric-icon')));
for(const key of ['total','ad','other','views','impressions']){const badge=document.createElement('span');badge.id='change-'+key;badge.className='metric-change neutral';badge.textContent='No comparison';badge.setAttribute('role','status');$(key).closest('article').append(badge);}
document.querySelectorAll('.metrics article').forEach(card=>{const top=document.createElement('div');top.className='metric-topline';const changes=document.createElement('div');changes.className='metric-changes';top.append(card.querySelector('.metric-icon'),changes);card.querySelectorAll('.metric-change').forEach(badge=>changes.append(badge));card.prepend(top);});
async function updateMetricChanges(data,requested,sequence){
  const params=new URLSearchParams(requested),first=params.get('start'),last=params.get('end');
  for(const key of ['total','ad','other','views','impressions']){$('change-'+key).textContent='Comparing';$('change-'+key).className='metric-change neutral';}
  $('change-ad').hidden=$('adMetric').hidden;$('change-other').hidden=$('sponsorMetric').hidden;
  if(!first||!last||!data.rows.length){for(const key of ['total','ad','other','views','impressions'])$('change-'+key).textContent='No comparison';window.QuickInsights?.render(data,requested,null,'none');return;}
  const span=(Date.parse(last)-Date.parse(first))/86400000+1,end=new Date(Date.parse(first)-86400000).toISOString().slice(0,10),start=new Date(Date.parse(first)-span*86400000).toISOString().slice(0,10);params.set('start',start);params.set('end',end);
  try{const previous=await api('/api/report?'+params);if(sequence!==requestNumber)return;
    window.QuickInsights?.render(data,requested,previous,'ready');
    const ids=params.getAll('channel'),coverage=new Set(previous.rows.map(row=>row.day+'|'+row.channel));
    const currentCoverage=new Set(data.rows.map(row=>row.day+'|'+row.channel));const complete=coverage.size===span*ids.length&&currentCoverage.size===span*ids.length;
    for(const key of ['total','ad','other','views','impressions']){const badge=$('change-'+key),before=previous.totals[key],now=data.totals[key];let label='No prior data',kind='neutral';if(previous.rows.length&&!complete)label='Partial data';else if(complete){if(before===0)label=now===0?'0%':'New';else{const change=(now-before)/Math.abs(before)*100;kind=Math.abs(change)<1?'steady':change>0?'up':'down';label=(change>0?'+':'')+(Math.abs(change)<1&&change!==0?change.toFixed(1):Math.round(change))+'%';}if(before===0&&now===0)kind='steady';}badge.textContent=(key==='ad'&&!$('sponsorMetric').hidden?'Ads ':key==='other'&&!$('adMetric').hidden?'Other ':'')+label;badge.className='metric-change '+kind;badge.title='Compared with '+start+' to '+end+' for the same selected channels. Changes below 1% are amber.';}
  }catch(error){if(sequence!==requestNumber||error.stale)return;for(const key of ['total','ad','other','views','impressions'])$('change-'+key).textContent='Unavailable';window.QuickInsights?.render(data,requested,null,'unavailable');}
}
const revenueLabel=$('total').previousElementSibling;revenueLabel.id='totalLabel';
for(const id of ['total','views','impressions','ad','other']){const value=$(id),label=value.previousElementSibling;label.before(value);}
const iconsScript=document.createElement('script');iconsScript.src='/static/lucide.min.js';iconsScript.onload=()=>lucide.createIcons();document.head.append(iconsScript);
const shareScript=document.createElement('script');shareScript.src='/static/revenue-share.js';shareScript.onload=()=>window.RevenueShare.render(reportRows);document.head.append(shareScript);
document.addEventListener('click',event=>{if(!rangePicker.contains(event.target))rangePicker.open=false;});
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&rangePicker.open){rangePicker.open=false;rangeTitle.focus();}});
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&$('channelPicker').open){$('channelPicker').open=false;$('channelSummary').focus();}});
document.addEventListener('click',e=>{if(!accountMenu.contains(e.target))accountMenu.open=false;});
menuPanel.querySelectorAll('[data-view]').forEach(button=>button.addEventListener('click',()=>{accountMenu.open=false;}));
const loading=document.createElement('div');loading.id='reportLoading';loading.hidden=true;loading.setAttribute('role','status');loading.innerHTML='<span class="loading-spinner" aria-hidden="true"></span><span>Updating data...</span>';document.body.append(loading);
let loadingTicket=0;
function setLoading(value){loading.hidden=!value;$('dashboard').setAttribute('aria-busy',String(value));}
const money=n=>new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:0,minimumFractionDigits:0}).format(n/100);
const number=n=>new Intl.NumberFormat('en-IN').format(n);
function fitMetricValues(){document.querySelectorAll('.metrics strong').forEach(value=>{value.style.fontSize='';let size=parseFloat(getComputedStyle(value).fontSize);while(value.scrollWidth>value.clientWidth&&size>18){size--;value.style.fontSize=size+'px';}});}
window.addEventListener('resize',()=>requestAnimationFrame(fitMetricValues));
lightStyle.addEventListener('load',fitMetricValues);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function notify(message){$('notice').textContent=message;$('notice').hidden=false;}
async function api(path,options={}){
  const epoch=accessEpoch;
  const headers={'X-CSRF-Token':csrf,...options.headers};
  if(options.body && !(options.body instanceof FormData)){headers['Content-Type']='application/json';options.body=JSON.stringify(options.body);}
  const response=await fetch(path,{...options,headers});
  const data=await response.json();
  if(epoch!==accessEpoch){const error=new Error('Access changed; stale response discarded.');error.stale=true;throw error;}
  if(!response.ok){if(response.status===401&&me)signOutView('Session ended. Sign in again.');const error=new Error(data.error||'Request failed.');error.status=response.status;throw error;}
  return data;
}
function bind(id,event,fn){$(id).addEventListener(event,async e=>{e.preventDefault();const button=e.submitter||((e.target.tagName==='BUTTON')?e.target:null);if(button)button.disabled=true;try{await fn(e);}catch(error){if(!error.stale){const dialog=e.target.closest('dialog');if(dialog?.open&&dialog.querySelector('.form-error'))dialog.querySelector('.form-error').textContent=error.message;else if(me)notify(error.message);else $('loginError').textContent=error.message;}}finally{if(button)button.disabled=false;}});}
function clearSensitive(){
  window.QuickInsights?.clear();
  document.querySelectorAll('.metric-change').forEach(badge=>{badge.textContent='No comparison';badge.className='metric-change neutral';});
  loadingTicket++;setLoading(false);
  clearTimeout(filterTimer);availableDates.replaceChildren();dateCoverage.textContent='';
  calendarDates=[];if(calendar){calendar.clear(false);calendar.set('enable',[]);}revenueLabel.textContent='Total Revenue';
  accessEpoch++;requestNumber++;reportRows=[];users=[];adminChannels=[];pending=null;appliedQuery='';latestDay='';pageIndex=0;
  for(const dialog of document.querySelectorAll('dialog[open]'))dialog.close();
  for(const id of ['records','history','users','channelDirectory','previewRows','assignments','channelOptions'])$(id).replaceChildren();
  for(const id of ['channelCount','total','ad','other','views','impressions','rowCount','period','pageInfo','appliedScope'])$(id).textContent='-';
  $('preview').hidden=true;$('export').disabled=true;$('userForm').reset();$('passwordForm').reset();$('uploadForm').reset();
  if(window.RevenueCharts)RevenueCharts.render([]);
  window.RevenueShare?.clear();
  window.DIYGraphs?.clear();
}
function signOutView(message){clearSensitive();me=null;csrf='';selectedChannels.clear();$('shell').hidden=true;$('login').hidden=false;$('loginError').textContent=message;}
function identity(value){
  me=value;csrf=value.csrf;$('login').hidden=true;$('shell').hidden=false;
  signedInName.textContent=value.user.username;
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
  $('channelSummary').textContent='Channels';
  const selection=size===0?'No channels selected':size===me.channels.length?'All assigned channels ('+size+')':size===1?me.channels.find(c=>selectedChannels.has(String(c.id))).name:size+' channels selected';
  $('channelSummary').title=selection;
  $('channelSummary').setAttribute('aria-label','Channels: '+selection);
}
function filterChannelOptions(){const text=$('channelSearch').value.trim().toLowerCase();for(const label of $('channelOptions').children)label.hidden=!label.textContent.toLowerCase().includes(text);}
function normalizeDateInputs(from,to){if(from.value&&to.value&&from.value>to.value){const earlier=to.value;to.value=from.value;from.value=earlier;}return {start:from.value,end:to.value};}
function dirty(){
  window.QuickInsights?.clear('Updating insights...');
  normalizeDateInputs($('start'),$('end'));
  clearTimeout(filterTimer);requestNumber++;$('export').disabled=true;
  $('filterState').textContent='Updating...';
  filterTimer=setTimeout(()=>{if(!me)return;refresh().catch(error=>{if(!error.stale)notify(error.message);});},300);
}
function query(){const params=new URLSearchParams(normalizeDateInputs($('start'),$('end')));if(!selectedChannels.size)params.append('channel','none');else for(const id of [...selectedChannels].sort((a,b)=>Number(a)-Number(b)))params.append('channel',id);return params.toString();}
function renderTable(){const size=Number($('pageSize').value),pages=Math.max(1,Math.ceil(reportRows.length/size));pageIndex=Math.min(pageIndex,pages-1);const subset=reportRows.slice(pageIndex*size,(pageIndex+1)*size);
  $('records').innerHTML=subset.map(r=>`<tr><td>${esc(r.day)}</td><td>${esc(r.channel)}</td><td class="number">${number(r.views)}</td><td class="number">${number(r.impressions)}</td><td class="number">${money(r.ad)}</td><td class="number">${money(r.other)}</td><td class="number"><strong>${money(r.total)}</strong></td></tr>`).join('');
  $('pageInfo').textContent=reportRows.length?`${pageIndex*size+1}-${Math.min((pageIndex+1)*size,reportRows.length)} of ${number(reportRows.length)}`:'0 records';$('previousPage').disabled=pageIndex===0;$('nextPage').disabled=pageIndex>=pages-1;
}
async function refresh(){
  const ticket=++loadingTicket;setLoading(true);
  try{return await loadReport();}finally{if(ticket===loadingTicket)setLoading(false);}
}
async function loadReport(){
  window.QuickInsights?.clear('Updating insights...');
  clearTimeout(filterTimer);
  const sequence=++requestNumber,requested=query(),scope=$('channelSummary').textContent;
  $('filterState').textContent='Loading...';$('export').disabled=true;
  let data;try{data=await api('/api/report?'+requested);}catch(error){if(error.stale)return;if(sequence===requestNumber){$('filterState').textContent='Could not apply filters';$('export').disabled=!appliedQuery;window.QuickInsights?.clear('Insights unavailable. Could not load the selected data.');}throw error;}
  if(sequence!==requestNumber)return;
  appliedQuery=requested;reportRows=data.rows;pageIndex=0;
  const dates=data.available_dates||[];
  calendarDates=dates;
  if(resetDateBounds){
    resetDateBounds=false;
    if(dates.length){$('start').value=dates[0];$('end').value=dates.at(-1);return loadReport();}
  }
  if(initialWeek&&dates.length&&!$('start').value&&!$('end').value){
    initialWeek=false;const last=dates.at(-1),first=new Date(last+'T00:00:00Z');first.setUTCDate(first.getUTCDate()-6);
    $('start').value=dates.find(day=>day>=first.toISOString().slice(0,10))||last;$('end').value=last;return loadReport();
  }
  initialWeek=false;
  if(dates.length){
    let adjusted=false;
    for(const id of ['start','end']){
      const value=$(id).value;
      if(value&&!dates.includes(value)){
        $(id).value=dates.reduce((best,day)=>Math.abs(Date.parse(day)-Date.parse(value))<Math.abs(Date.parse(best)-Date.parse(value))?day:best,dates[0]);adjusted=true;
      }
    }
    if(adjusted){notify('Date adjusted to the nearest available data date for the selected channels.');return loadReport();}
  }
  availableDates.replaceChildren(...dates.map(day=>{const option=document.createElement('option');option.value=day;return option;}));
  for(const id of ['start','end']){if(dates.length){$(id).min=dates[0];$(id).max=dates[dates.length-1];}else{$(id).removeAttribute('min');$(id).removeAttribute('max');}}
  latestDay=dates.at(-1)||'';
  dateCoverage.textContent=dates.length?'Available data: '+dates[0]+' to '+dates.at(-1)+' ('+dates.length+' days)':'No data for selected channels';
  if(data.rows.length)latestDay=data.rows.reduce((last,r)=>r.day>last?r.day:last,latestDay);
  for(const k of ['total','ad','other'])$(k).textContent=money(data.totals[k]);
  $('adMetric').hidden=data.totals.ad===0&&data.totals.other!==0;
  $('sponsorMetric').hidden=data.totals.other===0;
  const appliedIds=new Set(new URLSearchParams(requested).getAll('channel'));const appliedChannels=me.channels.filter(channel=>appliedIds.has(String(channel.id)));
  revenueLabel.textContent='TOTAL REVENUE ('+(appliedChannels.length===1?appliedChannels[0].name:appliedChannels.length+' Channels')+')';
  syncCalendar();
  rangeText.textContent=$('start').value&&$('end').value?new Intl.DateTimeFormat('en-GB',{day:'2-digit',month:'short',year:'numeric',timeZone:'UTC'}).format(new Date($('start').value+'T00:00:00Z'))+' - '+new Intl.DateTimeFormat('en-GB',{day:'2-digit',month:'short',year:'numeric',timeZone:'UTC'}).format(new Date($('end').value+'T00:00:00Z')):'Latest week';
  $('views').textContent=number(data.totals.views);$('impressions').textContent=number(data.totals.impressions);
  $('channelCount').textContent=number(new Set(data.rows.map(row=>row.channel)).size);
  requestAnimationFrame(fitMetricValues);
  renderTable();
  window.RevenueShare?.render(data.rows);
  $('rowCount').textContent=number(data.rows.length)+' records';$('empty').hidden=data.rows.length>0;
  $('period').textContent=data.rows.length?[...new Set(data.rows.map(r=>r.day))].sort().filter((v,i,a)=>i===0||i===a.length-1).join(' to '):'No data';
  const params=new URLSearchParams(requested);$('appliedScope').textContent=scope+' | '+(params.get('start')||'Beginning')+' to '+(params.get('end')||'Latest');
  $('filterState').textContent=query()===requested?'Updated':'Updating...';$('export').disabled=false;
  $('updated').textContent='Updated '+new Date().toLocaleTimeString('en-IN');
  window.QuickInsights?.render(data,requested);
  void updateMetricChanges(data,requested,sequence);
}
bind('loginForm','submit',async()=>{
  const values=Object.fromEntries(new FormData($('loginForm')));
  try{await api('/api/login',{method:'POST',body:values});$('loginError').textContent='';$('loginForm').reset();await session();}catch(error){if(!error.stale){if(me)notify(error.message);else $('loginError').textContent=error.message;}}
});
bind('logout','click',async()=>{await api('/api/logout',{method:'POST'});location.reload();});
bind('filters','submit',refresh);
bind('reset','click',async()=>{initialWeek=false;resetDateBounds=true;HTMLFormElement.prototype.reset.call($('filters'));$('channelSearch').value='';$('end').disabled=false;selectedChannels=new Set(me.channels.map(c=>String(c.id)));renderChannelOptions();await refresh();});
bind('export','click',async()=>{window.location.href='/api/export?'+appliedQuery;});
$('channelSearch').addEventListener('input',filterChannelOptions);
const selectAllChannels=document.createElement('button');
selectAllChannels.type='button';selectAllChannels.id='selectAllChannels';selectAllChannels.textContent='Select all';
$('selectVisible').before(selectAllChannels);
function selectShown(checked){for(const label of $('channelOptions').children)if(!label.hidden){const input=label.querySelector('input');input.checked=checked;if(checked)selectedChannels.add(input.value);else selectedChannels.delete(input.value);}channelSummary();dirty();}
$('selectVisible').hidden=true;$('clearChannels').textContent='Clear';
selectAllChannels.title='Select all search results';$('clearChannels').title='Clear search results';
bind('selectAllChannels','click',async()=>selectShown(true));
$('channelOptions').addEventListener('change',e=>{if(e.target.checked)selectedChannels.add(e.target.value);else selectedChannels.delete(e.target.value);channelSummary();dirty();});
bind('selectVisible','click',async()=>selectShown(true));
bind('clearChannels','click',async()=>selectShown(false));
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
  try{document.querySelectorAll('.view').forEach(v=>v.hidden=v.id!==button.dataset.view);document.querySelectorAll('[data-view]').forEach(b=>b.classList.toggle('active',b===button));$('notice').hidden=true;if(button.dataset.view==='uploads')await history();if(button.dataset.view==='admin')await loadUsers();if(['dashboard','insightsView'].includes(button.dataset.view))await refresh();if(button.dataset.view==='diyGraphs'){await window.DIYGraphs?.load();}}catch(e){notify(e.message);}
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
const forgot=document.createElement('button');forgot.type='button';forgot.className='forgot-password';forgot.textContent='Forgot password';$('loginForm').append(forgot);
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

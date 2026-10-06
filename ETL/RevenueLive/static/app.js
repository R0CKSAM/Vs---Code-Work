'use strict';
const themeStyle=document.createElement('link');themeStyle.rel='stylesheet';themeStyle.href='/static/dark.css';document.head.append(themeStyle);
const lightStyle=document.createElement('link');lightStyle.rel='stylesheet';lightStyle.href='/static/light.css';document.head.append(lightStyle);
const uploadsStyle=document.createElement('link');uploadsStyle.rel='stylesheet';uploadsStyle.href='/static/uploads.css';document.head.append(uploadsStyle);
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
  const width=Math.min(Math.max(rect.width,312),innerWidth-24);
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
let directoryChannels=[],channelEditBusy=false;
const channelDirectorySearch=document.createElement('input');channelDirectorySearch.type='search';channelDirectorySearch.id='channelDirectorySearch';channelDirectorySearch.placeholder='Search channels';channelDirectorySearch.setAttribute('aria-label','Search channel directory');$('channelDirectory').before(channelDirectorySearch);
let selectedChannels=new Set(),reportRows=[],appliedQuery='',pageIndex=0,latestDay='',requestNumber=0;
let accessEpoch=0,checkingAccess=false;
let filterTimer;
let initialWeek=true;
let resetDateBounds=false;
const signedInName=document.createElement('span');signedInName.id='signedInName';
const companyLabel=document.createElement('label');companyLabel.textContent='Company Name';
const companyInput=document.createElement('input');companyInput.name='company_name';companyInput.maxLength=120;companyInput.autocomplete='organization';companyLabel.append(companyInput);
$('userForm').elements.username.closest('label').before(companyLabel);
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
const revenueFinalization=document.createElement('p');revenueFinalization.id='revenueFinalization';document.querySelector('#dashboard .metrics').after(revenueFinalization);
const paramsMonth=(selected,fallback)=>selected||fallback||'';
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
const calendarStatus=document.createElement('p');calendarStatus.className='calendar-status';calendarStatus.setAttribute('role','status');rangePanel.append(calendarStatus);
let rangeStart=null,pendingRange=null;
const dateActions=document.createElement('div');dateActions.className='calendar-actions';
dateActions.innerHTML='<button type="button" id="allDateRange">All Range</button><button type="button" id="cancelDateRange">Cancel</button><button type="button" id="applyDateRange" class="primary" disabled>Apply Range</button>';rangePanel.append(dateActions);
function stageRange(days){pendingRange=days;rangeStart=null;calendar?.setDate(days,false);$('applyDateRange').disabled=!days?.length;calendarStatus.textContent=days?days.join(' to '):'Select start and end dates.';}
dateActions.querySelector('#allDateRange').onclick=()=>{if(calendarDates.length)stageRange([calendarDates[0],calendarDates.at(-1)]);};
dateActions.querySelector('#cancelDateRange').onclick=()=>{rangePicker.open=false;syncCalendar();};
dateActions.querySelector('#applyDateRange').onclick=()=>{if(!pendingRange)return;[$('start').value,$('end').value]=pendingRange;$('datePreset').value='custom';rangePicker.open=false;pendingRange=null;dirty();};
function autoRange(dates,_,instance){if(!rangeStart){pendingRange=null;$('applyDateRange').disabled=true;rangeStart=instance.latestSelectedDateObj||dates[0];if(rangeStart)instance.setDate([rangeStart],false);calendarStatus.textContent='Select the end date, then Apply Range.';return;}const end=dates.find(day=>day.getTime()!==rangeStart.getTime())||rangeStart;stageRange([rangeStart,end].map(day=>instance.formatDate(day,'Y-m-d')).sort());}
function syncCalendar(){if(!calendar)return;rangeStart=null;pendingRange=null;$('applyDateRange').disabled=true;$('allDateRange').disabled=!calendarDates.length;calendar.set('monthSelectorType','static');calendar.set('enable',calendarDates);calendar.setDate([$('start').value,$('end').value].filter(Boolean),false);if($('end').value)calendar.jumpToDate($('end').value);updateCalendarNav();calendarStatus.textContent=calendarDates.length?'Select start and end dates.':'No dates available for the selected channels.';}
const calendarStyle=document.createElement('link');calendarStyle.rel='stylesheet';calendarStyle.href='/static/flatpickr.min.css';document.head.insertBefore(calendarStyle,themeStyle);
const calendarScript=document.createElement('script');calendarScript.src='/static/flatpickr.min.js';calendarScript.onload=()=>{calendar=flatpickr(calendarInput,{inline:true,mode:'multiple',dateFormat:'Y-m-d',disableMobile:true,enable:[],onChange:autoRange});syncCalendar();};document.head.append(calendarScript);
rangePicker.addEventListener('toggle',()=>{if(rangePicker.open){$('channelPicker').open=false;syncCalendar();}});
rangePicker.append(rangePanel);$('filters').prepend(rangePicker);$('revenueHeader').append($('export'));
function icon(name,className=''){const tile=document.createElement('span');tile.className=className;tile.setAttribute('aria-hidden','true');const glyph=document.createElement('i');glyph.dataset.lucide=name;tile.append(glyph);return tile;}
const drawerHeading=document.createElement('div');drawerHeading.className='drawer-heading';
const drawerTitle=document.createElement('strong');drawerTitle.textContent='Menu';
closeMenu.replaceChildren(icon('x'));closeMenu.title='Close menu';closeMenu.setAttribute('aria-label','Close menu');
drawerHeading.append(drawerTitle,closeMenu);menuPanel.prepend(drawerHeading);
for(const [view,glyph] of Object.entries({dashboard:'layout-dashboard',insightsView:'sparkles',tabular:'table',diyGraphs:'chart-no-axes-combined',uploads:'upload',admin:'users-round'})){
  menuPanel.querySelector(`[data-view="${view}"]`)?.prepend(icon(glyph,'menu-icon'));
}
menuTitle.prepend(icon('chart-no-axes-combined','brand-icon'));
const headerArtwork=document.createElement('span');headerArtwork.className='header-wave-art';headerArtwork.setAttribute('aria-hidden','true');document.querySelector('#shell>header').prepend(headerArtwork);
rangeTitle.prepend(icon('calendar-days'));
$('export').replaceChildren(icon('download'));$('export').title='Download CSV';$('export').setAttribute('aria-label','Download CSV');
document.querySelectorAll('.metrics article').forEach((card,index)=>card.prepend(icon(['indian-rupee','chart-pie','eye','megaphone'][index],'metric-icon')));
for(const key of ['total','ad','other','views','impressions']){const badge=document.createElement('span');badge.id='change-'+key;badge.className='metric-change';badge.hidden=true;badge.setAttribute('role','status');$(key).closest('article').append(badge);}
document.querySelectorAll('.metrics article').forEach(card=>{const top=document.createElement('div');top.className='metric-topline';const changes=document.createElement('div');changes.className='metric-changes';top.append(card.querySelector('.metric-icon'),changes);card.querySelectorAll('.metric-change').forEach(badge=>changes.append(badge));card.prepend(top);});
async function updateMetricChanges(data,requested,sequence){
  const params=new URLSearchParams(requested),first=params.get('start'),last=params.get('end');
  document.querySelectorAll('.metric-change').forEach(badge=>{badge.hidden=true;badge.textContent='';badge.removeAttribute('title');});
  if(!first||!last||!data.rows.length){window.QuickInsights?.render(data,requested,null,'none');return;}
  const span=(Date.parse(last)-Date.parse(first))/86400000+1,end=new Date(Date.parse(first)-86400000).toISOString().slice(0,10),start=new Date(Date.parse(first)-span*86400000).toISOString().slice(0,10);params.set('start',start);params.set('end',end);
  try{const previous=await api('/api/report?'+params);if(sequence!==requestNumber)return;
    window.QuickInsights?.render(data,requested,previous,'ready');
    const ids=params.getAll('channel'),coverage=new Set(previous.rows.map(row=>row.day+'|'+row.channel));
    const currentCoverage=new Set(data.rows.map(row=>row.day+'|'+row.channel));const complete=coverage.size===span*ids.length&&currentCoverage.size===span*ids.length;
    window.RevenueShare?.compare(data,previous,complete);
    for(const key of ['total','ad','other','views','impressions']){
      const badge=$('change-'+key),before=previous.totals[key],now=data.totals[key];
      if(!complete||!previous.rows.length||!Number.isFinite(before)||!Number.isFinite(now)||(before===0&&now!==0))continue;
      if((key==='ad'&&$('adMetric').hidden)||(key==='other'&&$('sponsorMetric').hidden))continue;
      const change=before===0?0:(now-before)/Math.abs(before)*100;
      const kind=Math.abs(change)<1?'steady':change>0?'up':'down';
      const label=(change>0?'+':'')+(Math.abs(change)<1&&change!==0?change.toFixed(1):Math.round(change))+'%';
      const changeValue=document.createElement('span');changeValue.className='metric-change-value';changeValue.textContent=label;badge.replaceChildren(changeValue);
      const comparisonPeriod=document.createElement('small');comparisonPeriod.className='metric-comparison-period';comparisonPeriod.textContent='vs previous '+span+' '+(span===1?'day':'days');badge.append(comparisonPeriod);
      badge.className='metric-change '+kind;badge.hidden=false;
      badge.title='Compared with '+start+' to '+end+' for the same selected channels. Changes below 1% are amber.';
    }
    requestAnimationFrame(fitMetricValues);
  }catch(error){if(sequence!==requestNumber||error.stale)return;window.QuickInsights?.render(data,requested,null,'unavailable');}
}
const revenueLabel=$('total').previousElementSibling;revenueLabel.id='totalLabel';
for(const key of ['total','ad','other','views','impressions']){
  const value=$(key),label=value.previousElementSibling,card=value.closest('article');
  if(!['ad','other'].includes(key)){label.classList.add('metric-heading');card.querySelector('.metric-topline').append(label);}
  const row=document.createElement('div'),changes=document.createElement('div');
  row.className='metric-value-row';changes.className='metric-changes';
  value.before(row);changes.append($('change-'+key));row.append(value,changes);
}
const splitHeading=document.createElement('span');splitHeading.className='metric-heading';splitHeading.textContent='Revenue sources';
document.querySelector('.revenue-split .metric-topline').append(splitHeading);
document.querySelectorAll('.metric-topline>.metric-changes').forEach(node=>node.remove());
const iconsScript=document.createElement('script');iconsScript.src='/static/lucide.min.js';iconsScript.onload=()=>lucide.createIcons();document.head.append(iconsScript);
const comparisonScript=document.createElement('script');comparisonScript.src='/static/channel-comparison.js';comparisonScript.onload=()=>{const timelineScript=document.createElement('script');timelineScript.src='/static/timeline-data.js';timelineScript.onload=()=>{const shareScript=document.createElement('script');shareScript.src='/static/revenue-share.js';shareScript.onload=()=>{window.RevenueShare.setChannels(me?.channels||[]);window.RevenueShare.render(reportRows);};document.head.append(shareScript);};document.head.append(timelineScript);};document.head.append(comparisonScript);
document.addEventListener('click',event=>{if(!rangePicker.contains(event.target))rangePicker.open=false;});
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&rangePicker.open){rangePicker.open=false;rangeTitle.focus();}});
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&$('channelPicker').open){$('channelPicker').open=false;$('channelSummary').focus();}});
document.addEventListener('click',e=>{if(!accountMenu.contains(e.target))accountMenu.open=false;});
menuPanel.querySelectorAll('[data-view]').forEach(button=>button.addEventListener('click',()=>{accountMenu.open=false;}));
const loading=document.createElement('div');loading.id='reportLoading';loading.hidden=true;loading.setAttribute('role','status');loading.innerHTML='<span class="loading-spinner" aria-hidden="true"></span><span>Updating data...</span>';document.body.append(loading);
let loadingTicket=0;
function setLoading(value){loading.hidden=!value;$('dashboard').setAttribute('aria-busy',String(value));}
const money=n=>new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:1,minimumFractionDigits:1}).format(n/100);
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
  let data;
  try{
    if(!response.headers.get('Content-Type')?.includes('application/json'))throw new Error();
    data=await response.json();
  }catch{
    const error=new Error(response.status===404?'The application server needs an update. Restart RevenueLive and refresh this page.':'The server could not complete this request. Refresh the page or check the application server.');
    error.status=response.status;throw error;
  }
  if(epoch!==accessEpoch){const error=new Error('Access changed; stale response discarded.');error.stale=true;throw error;}
  if(!response.ok){if(response.status===401&&me)signOutView('Session ended. Sign in again.');const error=new Error(data.error||'Request failed.');error.status=response.status;if(Array.isArray(data.channel_issues)){error.channelIssues=data.channel_issues;error.channelOptions=data.channel_options;}throw error;}
  return data;
}
function bind(id,event,fn){$(id).addEventListener(event,async e=>{e.preventDefault();const button=e.submitter||((e.target.tagName==='BUTTON')?e.target:null);if(button)button.disabled=true;try{await fn(e);}catch(error){if(!error.stale){if(error.channelIssues)showUploadChannelIssues(error.channelIssues,error.channelOptions);const dialog=e.target.closest('dialog');if(dialog?.open&&dialog.querySelector('.form-error'))dialog.querySelector('.form-error').textContent=error.message;else if(me)notify(error.message);else $('loginError').textContent=error.message;}}finally{if(button)button.disabled=false;}});}
function clearSensitive(){
  channelResolutionDraft.clear();uploadChannelIssues=[];uploadChannelOptions=[];
  $('uploadChannelIssues').hidden=true;$('uploadChannelIssueRows').replaceChildren();
  window.QuickInsights?.clear();
  document.querySelectorAll('.metric-change').forEach(badge=>{badge.hidden=true;badge.textContent='';badge.removeAttribute('title');});
  loadingTicket++;setLoading(false);
  clearTimeout(filterTimer);availableDates.replaceChildren();dateCoverage.textContent='';
  calendarDates=[];if(calendar){calendar.clear(false);calendar.set('enable',[]);}revenueLabel.textContent='Total Revenue';
  accessEpoch++;requestNumber++;reportRows=[];users=[];adminChannels=[];pending=null;appliedQuery='';latestDay='';pageIndex=0;
  directoryChannels=[];$('channelEditForm').reset();$('channelLogoPreview').replaceChildren();
  for(const dialog of document.querySelectorAll('dialog[open]'))dialog.close();
  for(const id of ['records','history','users','channelDirectory','previewRows','assignments','channelOptions','reportingDates','auditEvents'])$(id).replaceChildren();
  uploadRows=[];reportingDateRows=[];pendingDelete=null;
  $('uploadLibraryError').hidden=true;$('uploadLibraryCount').textContent='';$('auditStatus').textContent='';
  auditRequest++;auditCategory='all';auditPage=1;auditPages=1;
  $('auditCategories').replaceChildren();$('auditPageStatus').textContent='';
  for(const id of ['uploadAllCount','uploadLiveCount','uploadArchivedCount'])$(id).textContent='0';
  for(const id of ['uploadDatesPanel','uploadAuditPanel'])$(id).open=false;
  for(const id of ['channelCount','total','ad','other','views','impressions','rowCount','period','pageInfo','appliedScope'])$(id).textContent='-';
  $('preview').hidden=true;$('export').disabled=true;$('userForm').reset();$('passwordForm').reset();$('uploadForm').reset();
  if(window.RevenueCharts)RevenueCharts.render([]);
  window.RevenueShare?.clear();
  window.DIYGraphs?.clear();
}
function signOutView(message){clearSensitive();me=null;csrf='';selectedChannels.clear();$('shell').hidden=true;$('login').hidden=false;$('loginError').textContent=message;window.history.replaceState(null,'','/login'+location.hash);}
function identity(value){
  if(value.home)window.history.replaceState(null,'',value.home+location.search+location.hash);
  me=value;csrf=value.csrf;$('login').hidden=true;$('shell').hidden=false;
  if(loginEntering){loginEntering=false;void loginMotion($('shell'),[{opacity:0,transform:'translateY(12px)'},{opacity:1,transform:'translateY(0)'}],380);}
  window.RevenueShare?.setChannels(value.channels);
  const company=document.createElement('strong');company.textContent=value.company_name||value.user.username;
  const username=document.createElement('small');username.textContent=value.user.username;username.hidden=!value.company_name;
  signedInName.replaceChildren(company,username);
  $('identity').textContent=(value.recovery_email||value.user.username)+' | '+(value.user.super_admin?'Super Admin':value.user.role);
  $('uploadNav').hidden=value.user.role==='viewer';$('adminNav').hidden=value.user.role!=='admin';
}
function overview(){document.querySelectorAll('.view').forEach(v=>v.hidden=v.id!=='dashboard');document.querySelectorAll('[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view==='dashboard'));}
function passwordPrompt(){
  const first=!!me.user.must_change;
  $('passwordForm').elements.email.value=me.recovery_email||'';
  $('passwordTitle').textContent=first?'Set your own password':'Change password';
  $('currentPasswordLabel').textContent=first?'Temporary password':'Current password';
  $('passwordCancel').hidden=first;$('passwordDialog').querySelector('.form-error').textContent='';
  if(!$('passwordDialog').open)$('passwordDialog').showModal();
}
function accessSignature(value){return JSON.stringify([value.user.id,value.user.username,value.user.role,value.user.super_admin,value.user.must_change,value.company_name,value.recovery_email,value.channels]);}
async function session(){
  const value=await api('/api/me');clearSensitive();identity(value);overview();
  selectedChannels=new Set(value.channels.map(c=>String(c.id)));renderChannelOptions();
  if(value.user.must_change){passwordPrompt();return;}
  $('passwordCancel').hidden=false;await refresh();
}
async function syncAccess(){
  if(!me||checkingAccess||uploadReviewBusy||channelEditBusy)return;
  checkingAccess=true;
  try{
    const value=await api('/api/me');
    if(uploadReviewBusy||channelEditBusy)return;
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
  const labelDate=value=>new Intl.DateTimeFormat('en-GB',{day:'2-digit',month:'short',year:'numeric',timeZone:'UTC'}).format(new Date(value+'T00:00:00Z'));
  rangeText.textContent=$('start').value&&$('end').value?labelDate($('start').value)+($('start').value===$('end').value?'':' - '+labelDate($('end').value)):'Latest week';
  rangeTitle.title=rangeText.textContent;
  $('views').textContent=number(data.totals.views);$('impressions').textContent=number(data.totals.impressions);
  $('channelCount').textContent=number(new Set(data.rows.map(row=>row.channel)).size);
  requestAnimationFrame(fitMetricValues);
  renderTable();
  window.RevenueShare?.render(data.rows);
  $('rowCount').textContent=number(data.rows.length)+' records';$('empty').hidden=data.rows.length>0;
  $('period').textContent=data.rows.length?[...new Set(data.rows.map(r=>r.day))].sort().filter((v,i,a)=>i===0||i===a.length-1).join(' to '):'No data';
  const monthLabel=day=>new Intl.DateTimeFormat('en-GB',{month:'long',year:'numeric',timeZone:'UTC'}).format(new Date(day+'T00:00:00Z'));
  const firstMonth=paramsMonth($('start').value,data.rows[0]?.day),lastMonth=paramsMonth($('end').value,data.rows.at(-1)?.day);
  revenueFinalization.textContent=(firstMonth&&lastMonth?'Reporting period: '+monthLabel(firstMonth)+' to '+monthLabel(lastMonth)+'. ':'')+'Final revenue figures shall be consolidated and finalized by the 15th of the succeeding month.';
  const params=new URLSearchParams(requested);$('appliedScope').textContent=scope+' | '+(params.get('start')||'Beginning')+' to '+(params.get('end')||'Latest');
  $('filterState').textContent=query()===requested?'Updated':'Updating...';$('export').disabled=false;
  $('updated').textContent='Updated '+new Date().toLocaleTimeString('en-IN');
  window.QuickInsights?.render(data,requested);
  void updateMetricChanges(data,requested,sequence);
}
$('toggleLoginPassword').addEventListener('click',()=>{
  const input=$('loginPassword'),button=$('toggleLoginPassword'),show=input.type==='password';
  input.type=show?'text':'password';button.setAttribute('aria-pressed',String(show));
  button.setAttribute('aria-label',show?'Hide password':'Show password');button.title=show?'Hide password':'Show password';
  button.replaceChildren(icon(show?'eye-off':'eye'));window.lucide?.createIcons();
});
let loginEntering=false;
async function loginMotion(element,frames,duration){
  if(matchMedia('(prefers-reduced-motion: reduce)').matches||!element.animate)return;
  await element.animate(frames,{duration,easing:'ease-out'}).finished.catch(()=>{});
}
bind('loginForm','submit',async()=>{
  const form=$('loginForm'),panel=form.closest('.login-panel'),button=form.querySelector('[type="submit"]');
  if(form.dataset.submitting)return;
  form.dataset.submitting='true';form.setAttribute('aria-busy','true');
  const original=button.innerHTML,values=Object.fromEntries(new FormData(form));
  panel.classList.remove('login-failed','login-success');$('loginError').textContent='';
  button.textContent='Logging In...';
  try{
    await api('/api/login',{method:'POST',body:values});
    panel.classList.add('login-success');button.textContent='Logged In';
    await loginMotion(panel,[{transform:'scale(1)'},{transform:'scale(1.015)',offset:.5},{transform:'scale(1)'}],280);
    form.reset();loginEntering=true;await session();
  }catch(error){
    loginEntering=false;panel.classList.remove('login-success');
    if(!error.stale){
      if(me)notify(error.message);
      else{
        $('loginError').textContent=error.message;panel.classList.add('login-failed');
        await loginMotion(panel,[{transform:'translateX(0)'},{transform:'translateX(-7px)'},{transform:'translateX(6px)'},{transform:'translateX(-4px)'},{transform:'translateX(0)'}],320);
        $('loginPassword').focus();
      }
    }
  }finally{delete form.dataset.submitting;form.removeAttribute('aria-busy');button.innerHTML=original;panel.classList.remove('login-success');}
});
$('loginForm').addEventListener('input',()=>{$('loginForm').closest('.login-panel').classList.remove('login-failed');});
bind('logout','click',async()=>{await api('/api/logout',{method:'POST'});location.reload();});
bind('filters','submit',refresh);
bind('reset','click',async()=>{initialWeek=false;resetDateBounds=true;HTMLFormElement.prototype.reset.call($('filters'));$('channelSearch').value='';$('end').disabled=false;selectedChannels=new Set(me.channels.map(c=>String(c.id)));renderChannelOptions();await refresh();});
bind('export','click',async()=>{window.location.href='/api/export?'+appliedQuery;});
$('channelSearch').addEventListener('input',filterChannelOptions);
const selectAllChannels=document.createElement('button');
selectAllChannels.type='button';selectAllChannels.id='selectAllChannels';selectAllChannels.textContent='Select All';
$('selectVisible').before(selectAllChannels);
function selectShown(checked){for(const label of $('channelOptions').children)if(!label.hidden){const input=label.querySelector('input');input.checked=checked;if(checked)selectedChannels.add(input.value);else selectedChannels.delete(input.value);}channelSummary();dirty();}
$('selectVisible').hidden=true;$('clearChannels').textContent='Clear';
selectAllChannels.title='Select all search results';$('clearChannels').title='Clear search results';
bind('selectAllChannels','click',async()=>selectShown(true));
$('channelOptions').addEventListener('change',e=>{if(e.target.checked)selectedChannels.add(e.target.value);else selectedChannels.delete(e.target.value);channelSummary();dirty();});
bind('selectVisible','click',async()=>selectShown(true));
bind('clearChannels','click',async()=>selectShown(false));
document.addEventListener('click',e=>{if(!e.composedPath().includes($('channelPicker')))$('channelPicker').open=false;});
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
let uploadChannelIssues=[];
let uploadChannelOptions=[];
let uploadReviewBusy=false;
const channelResolutionDraft=new Map();
function showUploadChannelIssues(issues,options=me?.channels||[]){
  uploadChannelIssues=issues;
  uploadChannelOptions=options;
  $('channelResolutionError').textContent='';
  const descriptions={
    unknown:['Not registered','Add a new channel or match an existing channel.'],
    unassigned:['Not assigned to you','If the file name is incorrect, select your assigned channel. Access to this existing channel still requires an admin.'],
    archived:['Archived','Select an active channel if the file name is incorrect, or ask an admin to restore this channel.'],
    ambiguous:['Conflicting channel names','Select the intended channel explicitly.']
  };
  $('uploadChannelIssueCount').textContent=`${number(issues.length)} channels to resolve`;
  const choices=options.map(channel=>`<option value="map:${Number(channel.id)}">${esc(channel.name)}</option>`).join('');
  $('uploadChannelIssueRows').innerHTML=issues.map((issue,index)=>{
    const [label,action]=descriptions[issue.status]||['Needs review','Ask an admin to review this channel.'];
    const rows=Array.isArray(issue.rows)?issue.rows:[];
    const locations=rows.length>10?`<details><summary>${number(rows.length)} rows</summary><span>${esc(rows.join(', '))}</span></details>`:esc(rows.join(', '));
    return `<tr><td data-label="Channel in file"><strong>${esc(issue.channel)}</strong></td><td data-label="Status"><span class="channel-issue-status">${label}</span></td><td data-label="Excel rows">${locations}</td><td data-label="Resolve channel"><input type="search" data-channel-target-search="${index}" aria-label="Search destination for ${esc(issue.channel)}" placeholder="Search destination channel"><select data-channel-resolution="${index}" aria-label="Resolve ${esc(issue.channel)}"><option value="">Choose an action</option><option value="keep">No change; keep unresolved</option>${issue.status==='unknown'?'<option value="create">Yes, add new channel</option>':''}<optgroup label="Existing channels available to you">${choices}</optgroup></select><input data-new-channel-name="${index}" aria-label="New channel name for ${esc(issue.channel)}" maxlength="120" value="${esc(issue.channel)}" hidden><small data-channel-target-count="${index}"></small><small>${action}</small></td></tr>`;
  }).join('');
  for(const [index,issue] of issues.entries()){
    const saved=channelResolutionDraft.get(issue.channel),select=$('uploadChannelIssueRows').querySelector(`[data-channel-resolution="${index}"]`);
    if(saved){select.value=saved.action==='create'?'create':`map:${saved.channel_id}`;$('uploadChannelIssueRows').querySelector(`[data-new-channel-name="${index}"]`).value=saved.name||issue.channel;}
    $('uploadChannelIssueRows').querySelector(`[data-new-channel-name="${index}"]`).hidden=select.value!=='create';
  }
  refreshChannelDestinations();
  for(const [index,issue] of issues.entries()){
    const saved=channelResolutionDraft.get(issue.channel);
    if(saved?.action==='map_new'){
      const target=issues.findIndex(item=>item.channel===saved.target_source);
      $('uploadChannelIssueRows').querySelector(`[data-channel-resolution="${index}"]`).value=`new:${target}`;
    }
  }
  $('channelIssueSearch').value='';filterChannelIssues();
  $('applyChannelResolutions').disabled=!$('uploadForm').querySelector('input[type=file]').files.length;
  $('uploadChannelIssues').hidden=false;
  $('uploadChannelIssues').scrollIntoView({behavior:'smooth',block:'start'});
}
const channelSearchKey=value=>String(value).normalize('NFKC').toLocaleLowerCase().replace(/\s+/g,' ').trim();
function filterChannelIssues(){
  const query=channelSearchKey($('channelIssueSearch').value);
  let visible=0,resolved=0;
  for(const [index,issue] of uploadChannelIssues.entries()){
    const select=$('uploadChannelIssueRows').querySelector(`[data-channel-resolution="${index}"]`);
    const row=select.closest('tr');row.hidden=!channelSearchKey(issue.channel).includes(query);
    if(!row.hidden)visible++;
    if(select.value&&select.value!=='keep')resolved++;
  }
  $('uploadChannelIssueCount').textContent=`${resolved} of ${uploadChannelIssues.length} chosen | ${visible} shown`;
  $('channelIssueEmpty').hidden=visible!==0;
}
function refreshChannelDestinations(){
  const body=$('uploadChannelIssueRows');
  const pendingChannels=uploadChannelIssues.flatMap((issue,index)=>{
    const choice=body.querySelector(`[data-channel-resolution="${index}"]`).value;
    const name=body.querySelector(`[data-new-channel-name="${index}"]`).value.trim();
    return choice==='create'&&name?[{value:`new:${index}`,name}]:[];
  });
  for(const [index,issue] of uploadChannelIssues.entries()){
    const select=body.querySelector(`[data-channel-resolution="${index}"]`),selected=select.value;
    const query=channelSearchKey(body.querySelector(`[data-channel-target-search="${index}"]`).value);
    const candidates=uploadChannelOptions.map(channel=>({value:`map:${channel.id}`,name:channel.name}));
    const newlyAdded=pendingChannels.filter(channel=>channel.value!==`new:${index}`);
    const matches=channel=>channel.value===selected||channelSearchKey(channel.name).includes(query);
    const option=channel=>`<option value="${esc(channel.value)}">${esc(channel.name)}</option>`;
    select.innerHTML='<option value="">Choose an action</option><option value="keep">No change; keep unresolved</option>'+
      (issue.status==='unknown'?'<option value="create">Yes, add new channel</option>':'')+
      `<optgroup label="New channels in this review">${newlyAdded.filter(matches).map(option).join('')}</optgroup>`+
      `<optgroup label="Existing channels available to you">${candidates.filter(matches).map(option).join('')}</optgroup>`;
    select.value=[...select.options].some(option=>option.value===selected)?selected:'';
    body.querySelector(`[data-channel-target-count="${index}"]`).textContent=query?
      `${[...candidates,...newlyAdded].filter(channel=>channelSearchKey(channel.name).includes(query)).length} matching destinations`:'';
    body.querySelector(`[data-new-channel-name="${index}"]`).hidden=select.value!=='create';
  }
  filterChannelIssues();
}
$('channelIssueSearch').addEventListener('input',filterChannelIssues);
$('uploadChannelIssueRows').addEventListener('change',event=>{
  const select=event.target.closest('[data-channel-resolution]');if(!select)return;
  $('channelResolutionError').textContent='';
  $('uploadChannelIssueRows').querySelector(`[data-new-channel-name="${select.dataset.channelResolution}"]`).hidden=select.value!=='create';
  refreshChannelDestinations();
});
$('uploadChannelIssueRows').addEventListener('input',event=>{
  $('channelResolutionError').textContent='';
  if(event.target.matches('[data-channel-target-search],[data-new-channel-name]'))refreshChannelDestinations();
});
$('uploadForm').querySelector('input[type=file]').addEventListener('change',()=>{channelResolutionDraft.clear();uploadChannelIssues=[];$('uploadChannelIssues').hidden=true;});
bind('cancelChannelResolutions','click',()=>{channelResolutionDraft.clear();uploadChannelIssues=[];$('uploadChannelIssues').hidden=true;$('uploadForm').reset();});
bind('applyChannelResolutions','click',async()=>{
  $('channelResolutionError').textContent='';
  for(const [index,issue] of uploadChannelIssues.entries()){
    const choice=$('uploadChannelIssueRows').querySelector(`[data-channel-resolution="${index}"]`).value;
    if(!choice||choice==='keep'){
      $('channelResolutionError').textContent=`Resolve every listed channel, including ${issue.channel}, or cancel and revise the file.`;
      $('channelIssueSearch').value='';filterChannelIssues();
      $('uploadChannelIssueRows').querySelector(`[data-channel-resolution="${index}"]`).focus();return;
    }
    const action=choice==='create'?{source:issue.channel,action:'create',name:$('uploadChannelIssueRows').querySelector(`[data-new-channel-name="${index}"]`).value.trim()}:
      choice.startsWith('new:')?{source:issue.channel,action:'map_new',target_source:uploadChannelIssues[Number(choice.slice(4))].channel}:
      {source:issue.channel,action:'map',channel_id:Number(choice.slice(4))};
    if(action.action==='create'&&!action.name){$('channelResolutionError').textContent='Enter a name for each new channel.';return;}
    channelResolutionDraft.set(issue.channel,action);
  }
  const actions=[...channelResolutionDraft.values()],count=actions.filter(action=>action.action==='create').length;
  if(!confirm(`Apply ${actions.length} channel resolutions${count?` and create ${count} new channels`:''}? New channels remain registered even if this preview is cancelled. Revenue is published only after review.`))return;
  try{await reviewUpload();}catch(error){if(error.channelIssues)showUploadChannelIssues(error.channelIssues,error.channelOptions);$('channelResolutionError').textContent=error.message;}
});
let previewPage=0;
const previewPageSize=100;
function previewValidation(row){
  const label=row.entry_kind==='exact'?'Exact duplicate':row.entry_kind==='multiple'?'Multiple entries':'Cannot publish';
  const blocked=row.blocking_error?`<strong>${label}</strong><small>${esc(row.blocking_error)}</small>`:'';
  const warning=row.warning?`<strong>Total mismatch</strong><small>File total (INR): ${esc(row.warning.supplied_total)}</small><small>Rounded file total: ${money(row.warning.rounded_supplied_total)}</small><small>Calculated total: ${money(row.total)}</small>`:'';
  const sources=row.source_entries;
  const combined=sources?`<strong>${number(row.combined_entries)} ${row.combined_entries===1?'entry retained':'entries combined'}${row.excluded_source_rows.length?`, ${number(row.excluded_source_rows.length)} ${row.excluded_source_rows.length===1?'copy':'copies'} skipped`:''}</strong><details class="source-entries"><summary>Original Excel rows (${number(sources.length)})</summary>${sources.map(source=>`<div><strong>Row ${number(source.source_row)}${row.excluded_source_rows.includes(source.source_row)?' - skipped':''}</strong><small>${esc(source.source_channel||source.channel)} | ${esc(source.day)}</small><small>Views: ${number(source.views)} | Impressions: ${number(source.impressions)}</small><small>Ads: ${money(source.ad)} | Other: ${money(source.other)} | Total: ${money(source.total)}</small>${source.warning?`<small>File total: ${esc(source.warning.supplied_total)}</small>`:''}</div>`).join('')}</details>`:'';
  return blocked+warning+combined||'Valid';
}
function renderUploadPreview(){
  if(!pending)return;
  const warnings=pending.rows.filter(row=>row.warning||row.blocking_error);
  const query=channelSearchKey($('previewSearch').value);
  const rows=($('previewOnlyWarnings').checked?warnings:pending.rows).filter(row=>!query||
    [row,...(row.source_entries||[])].some(source=>channelSearchKey([source.channel,source.source_channel||'',source.day,source.source_row||''].join(' ')).includes(query)));
  const pages=Math.max(1,Math.ceil(rows.length/previewPageSize));
  previewPage=Math.max(0,Math.min(previewPage,pages-1));
  const start=previewPage*previewPageSize;
  $('previewRows').innerHTML=rows.slice(start,start+previewPageSize).map((r,index)=>`<tr class="${r.blocking_error?'preview-blocked':r.warning?'preview-mismatch':''}"><td>${number(r.source_row??start+index+2)}</td><td>${esc(r.day)}</td><td>${esc(r.channel)}</td><td class="number">${number(r.views)}</td><td class="number">${number(r.impressions)}</td><td class="number">${money(r.ad)}</td><td class="number">${money(r.other)}</td><td class="number"><strong>${money(r.total)}</strong></td><td>${previewValidation(r)}</td></tr>`).join('');
  $('previewPageStatus').textContent=rows.length?`${number(start+1)}-${number(Math.min(start+previewPageSize,rows.length))} of ${number(rows.length)} rows`:'No matching rows';
  $('previewPrevious').disabled=previewPage===0;
  $('previewNext').disabled=previewPage>=pages-1;
}
function openUploadPreview(value){
  $('uploadChannelIssues').hidden=true;$('uploadChannelIssueRows').replaceChildren();
  pending=value;previewPage=0;$('previewSearch').value='';
  const changes=pending.channel_resolutions||pending.rows.flatMap(row=>row.source_entries||[row]).filter(row=>row.channel_resolution).map(row=>row.channel_resolution);
  const uniqueChanges=[...new Map(changes.map(change=>[change.source,change])).values()];
  $('previewChannelChanges').hidden=!uniqueChanges.length;
  $('previewChannelChanges').innerHTML=uniqueChanges.map(change=>`<div><strong>${change.action==='create'?'Added':'Matched'}:</strong> ${esc(change.source)} &rarr; ${esc(change.channel)}</div>`).join('');
  const count=pending.rows.filter(row=>row.warning).length;
  const blocked=pending.rows.filter(row=>row.blocking_error).length;
  const skipped=pending.rows.reduce((sum,row)=>sum+(row.excluded_source_rows?.length||0),0);
  const combined=pending.rows.filter(row=>row.combined_entries>1).length;
  $('entrySummary').hidden=!skipped&&!combined;
  $('entrySummary').textContent=[skipped?`${number(skipped)} exact duplicate ${skipped===1?'copy':'copies'} skipped.`:'',combined?`Different entries included in ${number(combined)} daily ${combined===1?'total':'totals'}.`:''].filter(Boolean).join(' ');
  $('preview').hidden=false;$('replace').checked=false;$('replaceLabel').hidden=pending.duplicates===0;
  $('acceptTotals').checked=false;$('acceptTotalsLabel').hidden=count===0;
  $('previewOnlyWarnings').checked=count+blocked>0;$('previewOnlyWarningsLabel').hidden=count+blocked===0;
  $('previewWarning').hidden=count+blocked===0;
  $('previewWarning').textContent=[count?`${number(count)} total mismatches. Acceptance publishes calculated totals instead of the file totals.`:'',blocked?'Daily totals could not be prepared. Reopen the preview to retry.':''].filter(Boolean).join(' ');
  $('publish').disabled=blocked>0;
  $('previewCount').textContent=number(pending.rows.length)+' rows | '+pending.duplicates+' replacements'+(count?' | '+count+' total mismatches':'')+(pending.unchanged?' | '+pending.unchanged+' unchanged':'');
  renderUploadPreview();
}
async function prepareUploadPreview(value){
  try{
    if(value.rows.some(row=>row.entry_group)){
      const prepared=await api('/api/uploads/'+value.id+'/consolidate',{method:'POST',body:{combine_entries:true,skip_exact_duplicates:true}});
      value={...value,...prepared};
    }
    openUploadPreview(value);
  }catch(error){
    if(!error.stale&&me)openUploadPreview(value);
    throw error;
  }
}
$('previewOnlyWarnings').addEventListener('change',()=>{previewPage=0;renderUploadPreview();});
$('previewSearch').addEventListener('input',()=>{previewPage=0;renderUploadPreview();});
$('previewPrevious').addEventListener('click',()=>{previewPage--;renderUploadPreview();});
$('previewNext').addEventListener('click',()=>{previewPage++;renderUploadPreview();});
async function reviewUpload(){
  if(uploadReviewBusy)throw new Error('Upload review is already in progress.');
  if(pending)throw new Error('Publish or cancel the current preview first.');
  uploadReviewBusy=true;
  try{
    $('notice').hidden=true;$('channelResolutionError').textContent='';
    const body=new FormData($('uploadForm'));body.set('channel_actions',JSON.stringify([...channelResolutionDraft.values()]));
    const result=await api('/api/uploads/preview',{method:'POST',body});
    if(me&&result.channels){
      const allSelected=me.channels.every(channel=>selectedChannels.has(String(channel.id)));
      me.channels=result.channels;
      window.RevenueShare?.setChannels(result.channels);
      selectedChannels=new Set(result.channels.filter(channel=>allSelected||selectedChannels.has(String(channel.id))).map(channel=>String(channel.id)));
      renderChannelOptions();
    }
    await prepareUploadPreview(result);channelResolutionDraft.clear();
    await history();
  }finally{uploadReviewBusy=false;}
}
bind('uploadForm','submit',reviewUpload);
bind('cancelUpload','click',async()=>{if(pending?.state==='pending')await api('/api/uploads/'+pending.id+'/reject',{method:'POST'});pending=null;$('preview').hidden=true;$('uploadForm').reset();await history();});
bind('publish','click',async()=>{
  if(!pending)return;if(pending.duplicates&&!$('replace').checked)throw new Error('Confirm replacement before publishing.');
  if(pending.rows.some(row=>row.blocking_error))throw new Error('Reopen the preview to prepare daily totals before publishing.');
  const warnings=pending.rows.filter(row=>row.warning).length;
  if(warnings&&!$('acceptTotals').checked)throw new Error('Accept the highlighted total mismatches before publishing calculated totals.');
  if(!confirm('Publish '+pending.rows.length+' revenue records'+(warnings?' using calculated totals for '+warnings+' highlighted mismatches':'')+(pending.duplicates?' and replace '+pending.duplicates+' existing records':'')+'?'))return;
  await api('/api/uploads/'+pending.id+'/'+(pending.state==='rejected'?'unarchive':'commit'),{method:'POST',body:{replace:$('replace').checked,accept_total_mismatches:$('acceptTotals').checked}});
  pending=null;$('preview').hidden=true;$('uploadForm').reset();notify('Data published.');await history();
});
let uploadRows=[],uploadFilter='all',pendingDelete=null;
let auditCategory='all',auditPage=1,auditPages=1,auditRequest=0;
const isUploadArchived=row=>!!row.archived||!['pending','committed'].includes(row.state);
const isUploadLive=row=>row.state==='committed'&&!isUploadArchived(row);
const uploadNumber=value=>Number.isFinite(value)?number(value):'-';
const uploadDate=day=>day?new Intl.DateTimeFormat('en-GB',{day:'2-digit',month:'short',year:'numeric',timeZone:'UTC'}).format(new Date(day+'T00:00:00Z')):'-';
const auditDetail=event=>{
  try{
    const detail=JSON.parse(event.detail);
    if(detail && typeof detail==='object' && detail.username)return [detail.username,detail.role,
      typeof detail.active==='boolean'?(detail.active?'active':'disabled'):'',detail.password_reset?'Password reset':''].filter(Boolean).join(' | ');
    if(!detail || typeof detail!=='object' || !detail.filename)return event.detail;
    const count=Number.isInteger(detail.rows)?`${number(detail.rows)} rows`:Number.isInteger(detail.changed)?`${number(detail.changed)} changed rows`:Number.isInteger(detail.affected)?`${number(detail.affected)} live rows affected`:'';
    return [detail.filename,count,`#${String(detail.id||'').slice(0,8)}`].filter(Boolean).join(' | ');
  }catch{return event.detail;}
};
let reportingDateRows=[];
const renderReportingDates=()=>{
  const search=$('dateSearch').value;
  const rows=search?reportingDateRows.filter(row=>row.day===search):$('showAllDates').checked?reportingDateRows:reportingDateRows.slice(0,30);
  $('reportingDates').innerHTML=rows.map(row=>`<tr><td data-label="Date"><strong>${esc(row.day)}</strong></td><td data-label="Channels">${number(row.channels)}</td><td data-label="Status"><span class="status-pill status-${row.hidden?'restored':'committed'}">${row.hidden?'Hidden':'Live'}</span></td><td data-label="Action"><button type="button" data-date="${esc(row.day)}" data-hidden="${row.hidden?'false':'true'}">${row.hidden?'Restore':'Hide'}</button></td></tr>`).join('')||'<tr><td colspan="4">No reporting dates found.</td></tr>';
};
const loadUploadAdmin=async()=>{
  const tasks=[];
  if($('uploadDatesPanel').open)tasks.push((async()=>{
    try{const dates=await api('/api/admin/dates');reportingDateRows=dates.rows;renderReportingDates();}
    catch(error){if(!error.stale)$('reportingDates').innerHTML=`<tr><td colspan="4">${esc(error.message)}</td></tr>`;}
  })());
  if($('uploadAuditPanel').open)tasks.push(loadAuditHistory());
  await Promise.allSettled(tasks);
};
async function loadAuditHistory(){
  const version=++auditRequest;
  $('auditEvents').innerHTML='<tr><td colspan="4">Loading activity...</td></tr>';
  $('auditPrevious').disabled=true;$('auditNext').disabled=true;
  try{
    const audit=await api('/api/admin/audit?'+new URLSearchParams({category:auditCategory,page:auditPage}));
    if(version!==auditRequest)return;
    auditPage=audit.page;auditPages=audit.pages;
    $('auditStatus').classList.toggle('audit-invalid',!audit.valid);
    $('auditStatus').textContent=(audit.valid?'History verified':'History verification failed')+' | '+number(audit.count)+' events';
    $('auditStatus').title='Audit head: '+audit.head;
    $('auditCategories').innerHTML=audit.categories.map(category=>`<button type="button" data-audit-category="${esc(category.id)}" aria-pressed="${category.id===auditCategory}">${esc(category.label)} <span>${number(category.count)}</span></button>`).join('');
    $('auditPageStatus').textContent=audit.total?`${number((audit.page-1)*audit.page_size+1)}-${number((audit.page-1)*audit.page_size+audit.events.length)} of ${number(audit.total)} events`:'No events in this category';
    $('auditPrevious').disabled=auditPage<=1;$('auditNext').disabled=auditPage>=auditPages;
    $('auditEvents').innerHTML=audit.events.map(event=>`<tr><td data-label="When">${esc(new Date(event.created).toLocaleString('en-IN'))}</td><td data-label="User"><strong>${esc(event.actor)}</strong></td><td data-label="Action">${esc(event.action.replaceAll('_',' '))}</td><td data-label="Detail" title="${esc(event.detail)}">${esc(auditDetail(event))}</td></tr>`).join('')||'<tr><td colspan="4">No activity in this category.</td></tr>';
  }catch(error){if(!error.stale&&version===auditRequest){$('auditStatus').textContent=error.message;$('auditStatus').classList.add('audit-invalid');$('auditEvents').replaceChildren();$('auditPageStatus').textContent='Activity could not be loaded.';}}
}
$('auditCategories').addEventListener('click',event=>{
  const button=event.target.closest('[data-audit-category]');if(!button)return;
  auditCategory=button.dataset.auditCategory;auditPage=1;loadAuditHistory();
});
$('auditPrevious').addEventListener('click',()=>{if(auditPage>1){auditPage--;loadAuditHistory();}});
$('auditNext').addEventListener('click',()=>{if(auditPage<auditPages){auditPage++;loadAuditHistory();}});
const renderUploadRows=()=>{
  const admin=me?.user.role==='admin',search=$('uploadSearch').value.trim().toLowerCase();
  const counts={all:uploadRows.length,live:uploadRows.filter(isUploadLive).length,archived:uploadRows.filter(isUploadArchived).length};
  for(const [key,id] of Object.entries({all:'uploadAllCount',live:'uploadLiveCount',archived:'uploadArchivedCount'}))$(id).textContent=number(counts[key]);
  document.querySelectorAll('[data-upload-filter]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.uploadFilter===uploadFilter)));
  const rows=uploadRows.filter(row=>(uploadFilter==='all'||(uploadFilter==='archived'?isUploadArchived(row):isUploadLive(row)))&&(!search||`${row.filename} ${row.username}`.toLowerCase().includes(search)));
  $('history').innerHTML=rows.map(row=>{
    const awaitingReview=row.state==='pending',archived=isUploadArchived(row),status=awaitingReview?'Pending review':archived?'Archived':row.live_rows===0?'Replaced':row.visible_rows===0?'Hidden':'Live';
    const note=awaitingReview?'Review and publish to show on dashboard':archived?'Not shown on dashboard':row.live_rows===0?'A newer file contains these records':row.visible_rows===0?'Date or channel is hidden':`${uploadNumber(row.visible_rows)} records on dashboard`;
    const action=awaitingReview?'review':archived?'unarchive':'archive',label=awaitingReview?'Review':archived?'Unarchive':'Archive';
    const buttons=admin||awaitingReview?`<button type="button" class="upload-visibility" data-upload-action="${action}" data-id="${esc(row.id)}" title="${awaitingReview?'Review before publishing':archived?'Show this file data on the dashboard':'Hide this file data from the dashboard'}"><i data-lucide="${awaitingReview?'file-search':archived?'archive-restore':'archive'}" aria-hidden="true"></i>${label}</button>`:'';
    const deletion=admin?`<button type="button" class="upload-danger" data-upload-action="delete" data-id="${esc(row.id)}" title="Delete uploaded file"><i data-lucide="trash-2" aria-hidden="true"></i>Delete</button>`:'';
    return `<tr><td data-label="File"><div class="upload-file-cell"><span class="upload-file-icon" aria-hidden="true"><i data-lucide="file-spreadsheet"></i></span><div><a class="upload-file-name" href="/api/uploads/${esc(row.id)}/file" title="Download ${esc(row.filename)}">${esc(row.filename)}</a><small>${esc(row.username)} &middot; ${esc(new Date(row.created).toLocaleString('en-IN',{day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'}))}</small></div></div></td><td data-label="Period"><div><strong>${uploadDate(row.start)}${row.end&&row.end!==row.start?` &ndash; ${uploadDate(row.end)}`:''}</strong><small>${uploadNumber(row.channel_count)} channels</small></div></td><td data-label="Records" class="number"><strong>${uploadNumber(row.total_rows)}</strong></td><td data-label="Dashboard"><div><span class="status-pill status-${archived?'archived':status==='Live'?'committed':'unknown'}">${status}</span><small>${note}</small></div></td><td data-label="Actions"><div class="upload-actions">${buttons}${deletion}</div></td></tr>`;
  }).join('')||`<tr><td colspan="5" class="upload-empty"><i data-lucide="folder-open" aria-hidden="true"></i><strong>${search?'No matching files':'No '+(uploadFilter==='all'?'uploaded':uploadFilter)+' files'}</strong></td></tr>`;
  $('uploadLibraryCount').textContent=number(rows.length)+' '+(rows.length===1?'file':'files')+(search?' matching search':'');
  window.lucide?.createIcons();
};
const history=async()=>{
  $('uploadAdminControls').hidden=me.user.role!=='admin';$('uploadLibraryError').hidden=true;
  try{
    const data=await api('/api/uploads?show_archived=1');
    if(data.uploads_version!==2)throw new Error('Uploads needs the updated application server. Restart RevenueLive and refresh this page.');
    uploadRows=data.rows.filter(row=>!row.file_deleted);renderUploadRows();
    if(me.user.role==='admin')await loadUploadAdmin();
  }catch(error){if(!error.stale&&me){uploadRows=[];renderUploadRows();$('uploadLibraryError').textContent=error.message;$('uploadLibraryError').hidden=false;}}
};
$('uploadSearch').addEventListener('input',renderUploadRows);
document.querySelectorAll('[data-upload-filter]').forEach(button=>button.addEventListener('click',()=>{uploadFilter=button.dataset.uploadFilter;renderUploadRows();}));
for(const id of ['uploadDatesPanel','uploadAuditPanel'])$(id).addEventListener('toggle',()=>{if($(id).open&&me?.user.role==='admin')void loadUploadAdmin();});
$('dateSearch').addEventListener('change',renderReportingDates);
$('showAllDates').addEventListener('change',renderReportingDates);
$('reportingDates').addEventListener('click',async e=>{
  const button=e.target.closest('[data-date]');if(!button)return;
  const hidden=button.dataset.hidden==='true',day=button.dataset.date;
  if(!confirm((hidden?'Hide':'Restore')+' '+day+' for all dashboard users and channels?'))return;
  button.disabled=true;
  try{await api('/api/admin/dates/'+day+'/visibility',{method:'POST',body:{hidden}});await history();notify(hidden?'Date hidden from reports.':'Date restored in reports.');}
  catch(error){notify(error.message);}finally{button.disabled=false;}
});
$('history').addEventListener('click',async e=>{
  const button=e.target.closest('[data-upload-action]');if(!button)return;
  const action=button.dataset.uploadAction,id=button.dataset.id,row=uploadRows.find(item=>item.id===id);if(!row)return;
  if(action==='delete'){pendingDelete=id;$('uploadDeleteName').textContent=row.filename;$('uploadDeleteDialog').querySelector('.form-error').textContent='';$('uploadDeleteDialog').showModal();return;}
  if(action==='review'||action==='unarchive'&&['pending','rejected'].includes(row.state)&&(row.warning_count>0||row.blocking_count>0)){
    if(pending&&pending.id!==id){notify('Publish or cancel the current preview first.');return;}
    button.disabled=true;
    try{await prepareUploadPreview(await api('/api/uploads/'+id+'/preview'));$('preview').scrollIntoView({behavior:'smooth',block:'start'});}
    catch(error){if(error.channelIssues)showUploadChannelIssues(error.channelIssues,error.channelOptions);notify(error.message);}finally{button.disabled=false;}
    return;
  }
  if(action==='unarchive'&&['pending','rejected'].includes(row.state)&&row.replacements>0&&!confirm(`Publish ${row.filename} and replace ${row.replacements} existing date/channel records?`))return;
  button.disabled=true;
  try{
    const endpoint=me.user.role!=='admin'?'commit':action;
    await api('/api/uploads/'+id+'/'+endpoint,{method:'POST',body:action==='archive'?{archived:true}:{replace:row.replacements>0}});
    if(pending?.id===id){pending=null;$('preview').hidden=true;$('uploadForm').reset();}
    await history();notify(action==='archive'?row.filename+' archived. Its data is hidden.':row.filename+' unarchived.');
  }
  catch(error){notify(error.message);}finally{button.disabled=false;}
});
bind('uploadDeleteCancel','click',async()=>{$('uploadDeleteDialog').close();pendingDelete=null;});
bind('uploadDeleteForm','submit',async()=>{
  if(!pendingDelete)return;
  const id=pendingDelete;await api('/api/uploads/'+id+'/delete',{method:'POST'});
  if(pending?.id===id){pending=null;$('preview').hidden=true;$('uploadForm').reset();}
  $('uploadDeleteDialog').close();pendingDelete=null;await history();notify('File deleted.');
});
let accountEmailEnabled=false,userStatusFilter='active';
const userStatusTabs=document.createElement('div');userStatusTabs.className='user-status-tabs';userStatusTabs.setAttribute('role','group');userStatusTabs.setAttribute('aria-label','User status');
for(const [key,label] of [['active','Active'],['inactive','Inactive'],['all','All']]){const button=document.createElement('button');button.type='button';button.dataset.userStatus=key;button.textContent=label;button.onclick=()=>{userStatusFilter=key;renderUserRows();};userStatusTabs.append(button);}
$('admin').querySelector('.table-wrap').before(userStatusTabs);
function renderUserRows(){
  const active=new Set(adminChannels.map(c=>c.id));
  const scope=u=>{const count=u.channels.filter(id=>active.has(id)).length;return u.role==='admin'?'All channels':count===0?'No channels':count===active.size?'All assigned channels ('+count+')':count+' of '+active.size+' channels';};
  const privilege=u=>u.super_admin?3:({viewer:0,uploader:1,admin:2})[u.role]??4;
  const compareText=(a,b)=>String(a||'').localeCompare(String(b||''),'en',{sensitivity:'base',numeric:true});
  const filtered=users.filter(u=>userStatusFilter==='all'||!!u.active===(userStatusFilter==='active')).sort((a,b)=>Number(!!b.active)-Number(!!a.active)||privilege(a)-privilege(b)||compareText(a.company_name,b.company_name)||compareText(a.username,b.username)||a.id-b.id);
  for(const button of userStatusTabs.children){const key=button.dataset.userStatus;button.setAttribute('aria-pressed',String(key===userStatusFilter));button.textContent=({active:'Active',inactive:'Inactive',all:'All'})[key]+' ('+users.filter(u=>key==='all'||!!u.active===(key==='active')).length+')';}
$('users').innerHTML=filtered.map(u=>`<tr><td>${u.company_name?esc(u.company_name):'Not set'}</td><td><strong>${esc(u.username)}</strong><small class="user-recovery-email">${u.email?esc(u.email):'Email not set'}</small></td><td><span class="role-pill role-${u.super_admin?'super':['admin','uploader','viewer'].includes(u.role)?u.role:'unknown'}">${u.super_admin?'Super Admin':esc(u.role)}</span></td><td>${scope(u)}</td><td><span class="status-pill status-${!u.active?'disabled':u.must_change?'pending':'enabled'}">${!u.active?'Disabled':u.must_change?'Password setup pending':'Enabled'}</span></td><td>${(u.super_admin&&u.id!==me.user.id)||(!me.user.super_admin&&u.role==='admin')?'Protected':`<button data-user="${u.id}">Edit</button>`}</td></tr>`).join('')||'<tr><td colspan="6">No users in this category.</td></tr>';
}

async function loadUsers(){
  const data=await api('/api/admin/users');users=data.users;adminChannels=data.channels;accountEmailEnabled=!!data.email_enabled;
  renderUserRows();
  $('userForm').elements.role.querySelector('option[value="admin"]').disabled=!me.user.super_admin;
  directoryChannels=[...data.channels.map(c=>({...c,archived:false})),...(data.archived||[]).map(c=>({...c,archived:true}))];
  renderChannelDirectory();
}
function renderChannelDirectory(){
  const search=$('channelDirectorySearch').value.trim().toLowerCase();
  const rows=directoryChannels.filter(c=>c.name.toLowerCase().includes(search));
  $('channelDirectory').innerHTML=rows.map(c=>`<div class="channel-directory-row"><span class="directory-logo" data-directory-logo="${c.id}"></span><span class="directory-channel-name"><strong>${esc(c.name)}</strong><small>${c.archived?'Archived':'Active'}</small></span><span class="channel-directory-actions"><button type="button" data-edit-channel="${c.id}" title="Edit name and logo for ${esc(c.name)}" aria-label="Edit ${esc(c.name)}"><i data-lucide="pencil" aria-hidden="true"></i></button><button type="button" data-channel="${c.id}" data-archived="${!c.archived}" title="${c.archived?'Restore':'Archive'} ${esc(c.name)}" aria-label="${c.archived?'Restore':'Archive'} ${esc(c.name)}"><i data-lucide="${c.archived?'archive-restore':'archive'}" aria-hidden="true"></i></button></span></div>`).join('')||'<p>No matching channels.</p>';
  for(const channel of rows)window.RevenueShare?.brandLogo($('channelDirectory').querySelector(`[data-directory-logo="${channel.id}"]`),channel.name,channel);
  window.lucide?.createIcons();
}
$('channelDirectorySearch').addEventListener('input',renderChannelDirectory);
$('channelDirectory').addEventListener('click',event=>{
  const button=event.target.closest('[data-edit-channel]');if(!button)return;
  const channel=directoryChannels.find(c=>c.id===Number(button.dataset.editChannel));if(!channel)return;
  const form=$('channelEditForm');form.reset();form.elements.id.value=channel.id;form.elements.name.value=channel.name;
  form.querySelector('.form-error').textContent='';$('channelLogoPreview').replaceChildren();
  window.RevenueShare?.brandLogo($('channelLogoPreview'),channel.name,channel);
  $('channelEditDialog').showModal();
});
function previewChannelLogo(){
  const form=$('channelEditForm'),file=form.elements.logo.files[0],preview=$('channelLogoPreview');
  form.querySelector('.form-error').textContent='';
  if(!file){const channel=directoryChannels.find(c=>c.id===Number(form.elements.id.value));if(channel)window.RevenueShare?.brandLogo(preview,channel.name,channel);return;}
  if(file.size>2*1024*1024||!['image/png','image/jpeg','image/webp'].includes(file.type)){
    form.querySelector('.form-error').textContent='Choose a PNG, JPG or WebP logo up to 2 MB.';form.elements.logo.value='';return;
  }
  form.elements.reset_logo.checked=false;
  const reader=new FileReader();reader.onload=()=>{if(form.elements.logo.files[0]!==file)return;const image=new Image();image.alt='Selected channel logo';image.src=reader.result;preview.replaceChildren(image);};reader.readAsDataURL(file);
}
$('channelEditForm').elements.logo.addEventListener('change',previewChannelLogo);
$('channelEditForm').elements.reset_logo.addEventListener('change',()=>{
  if($('channelEditForm').elements.reset_logo.checked){$('channelEditForm').elements.logo.value='';$('channelLogoPreview').textContent='Default';}else previewChannelLogo();
});
bind('channelEditCancel','click',async()=>{$('channelEditDialog').close();});
bind('channelEditForm','submit',async()=>{
  const form=$('channelEditForm'),body=new FormData(form);body.set('reset_logo',String(form.elements.reset_logo.checked));
  channelEditBusy=true;
  try{
    await api('/api/admin/channels/'+form.elements.id.value,{method:'POST',body});
    identity(await api('/api/me'));renderChannelOptions();
    $('channelEditDialog').close();await loadUsers();notify('Channel name and logo saved. Existing data and assignments retained.');
  }finally{channelEditBusy=false;}
});
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
function editUser(user){const form=$('userForm');form.reset();form.elements.id.value=user?.id||'';form.elements.username.value=user?.username||'';form.elements.company_name.value=user?.company_name||'';form.elements.email.value=user?.email||'';form.elements.role.value=user?.role||'viewer';form.elements.active.checked=user?!!user.active:true;form.elements.password.required=!user;form.elements.password.type='password';$('temporaryPasswordLabel').textContent=user?'Reset password (optional, 8+ characters)':'Temporary password (8+ characters)';$('userTitle').textContent=user?'Edit user':'Add user';$('userDialog').querySelector('.form-error').textContent='';$('assignmentSearch').value='';$('assignments').innerHTML=adminChannels.map(c=>`<label class="check"><input type="checkbox" value="${c.id}" ${user?.channels.includes(c.id)?'checked':''}>${esc(c.name)}</label>`).join('');assignmentSummary();assignmentRole();inviteMode();for(const name of ['role','active','password'])form.elements[name].disabled=!!user?.super_admin;$('showTemporary').closest('label').hidden=!!user?.super_admin;form.elements.password.closest('label').hidden=!!user?.super_admin;$('userDialog').showModal();}
bind('addUser','click',async()=>editUser());
$('users').addEventListener('click',e=>{const button=e.target.closest('[data-user]');if(button)editUser(users.find(u=>u.id===Number(button.dataset.user)));});
bind('userCancel','click',async()=>$('userDialog').close());
$('assignmentSearch').addEventListener('input',()=>{const search=$('assignmentSearch').value.trim().toLowerCase();for(const label of $('assignments').children)label.hidden=!label.textContent.toLowerCase().includes(search);assignmentSummary();});
$('assignments').addEventListener('change',assignmentSummary);
$('userForm').elements.role.addEventListener('change',assignmentRole);
$('showTemporary').addEventListener('change',()=>{$('userForm').elements.password.type=$('showTemporary').checked?'text':'password';});
for(const [id,checked] of [['assignAll',true],['assignClear',false]])bind(id,'click',async()=>{for(const label of $('assignments').children)if(!label.hidden)label.querySelector('input').checked=checked;assignmentSummary();});
bind('userForm','submit',async()=>{const form=$('userForm');const body={invite:$('inviteEmail').checked,id:form.elements.id.value?Number(form.elements.id.value):null,username:form.elements.username.value,company_name:form.elements.company_name.value,email:form.elements.email.value,role:form.elements.role.value,password:$('inviteEmail').checked?'':form.elements.password.value,active:form.elements.active.checked,channels:form.elements.role.value==='admin'?[]:[...$('assignments').querySelectorAll('input:checked')].map(c=>Number(c.value))};const result=await api('/api/admin/users',{method:'POST',body});$('userDialog').close();form.reset();await loadUsers();identity(await api('/api/me'));notify(result.warning|| (body.invite?'Invitation sent. User will set their own password.':body.id?'User access saved. Open clients update automatically.':'User created: '+body.username.trim()+'. Sign-in address: '+location.origin+'/'));});
bind('channelForm','submit',async()=>{await api('/api/admin/channels',{method:'POST',body:Object.fromEntries(new FormData($('channelForm')))});$('channelForm').reset();await loadUsers();notify('Channel added.');});
const inviteLabel=document.createElement('label');inviteLabel.className='check';
inviteLabel.innerHTML='<input type="checkbox" id="inviteEmail">Invite by email';
const recoveryLabel=document.createElement('label');
recoveryLabel.innerHTML='Email<input name="email" type="email" required maxlength="80" autocomplete="off">';
const ownRecoveryLabel=recoveryLabel.cloneNode(true);
$('passwordForm').elements.confirm.closest('label').after(ownRecoveryLabel);
const deliveryStatus=document.createElement('p');deliveryStatus.className='muted';deliveryStatus.setAttribute('role','status');
$('userForm').elements.username.closest('label').after(recoveryLabel,inviteLabel,deliveryStatus);
function inviteMode(){const form=$('userForm'),editing=!!form.elements.id.value;form.elements.email.required=!editing||form.elements.active.checked;inviteLabel.hidden=editing;$('inviteEmail').disabled=!accountEmailEnabled;if(editing||!accountEmailEnabled)$('inviteEmail').checked=false;const enabled=$('inviteEmail').checked,protectedProfile=editing&&form.elements.password.disabled;form.elements.password.required=!editing&&!enabled;form.elements.password.closest('label').hidden=enabled||protectedProfile;form.elements.username.type='text';$('showTemporary').closest('label').hidden=enabled||protectedProfile;deliveryStatus.hidden=accountEmailEnabled;deliveryStatus.textContent='Email delivery not configured. Administrator password reset is available.';}
$('inviteEmail').addEventListener('change',inviteMode);
$('userForm').elements.active.addEventListener('change',inviteMode);
new MutationObserver(inviteMode).observe($('userDialog'),{attributes:true,attributeFilter:['open']});
const resetDialog=document.createElement('dialog');resetDialog.id='accountDialog';
resetDialog.innerHTML='<form id="accountForm"><h2 id="accountTitle">Forgot password</h2><label id="accountEmailLabel">Email<input name="email" type="email" required autocomplete="email"></label><label id="accountPasswordLabel" hidden>New password<input name="password" type="password" minlength="8" maxlength="256" autocomplete="new-password"></label><label id="accountConfirmLabel" hidden>Confirm password<input name="confirm" type="password" autocomplete="new-password"></label><p class="form-error" role="alert"></p><div class="actions"><button class="primary">Continue</button><button type="button" id="accountCancel">Cancel</button></div></form>';
document.body.append(resetDialog);
let accountToken=new URLSearchParams(location.hash.slice(1)).get('account-token')||'';
if(accountToken)window.history.replaceState(null,'',location.pathname+location.search);
function openAccount(){const form=$('accountForm');form.reset();$('accountTitle').textContent=accountToken?'Set your password':'Forgot password';$('accountEmailLabel').hidden=!!accountToken;$('accountPasswordLabel').hidden=!accountToken;$('accountConfirmLabel').hidden=!accountToken;form.elements.email.required=!accountToken;form.elements.password.required=!!accountToken;form.elements.confirm.required=!!accountToken;resetDialog.querySelector('.form-error').textContent='';resetDialog.showModal();}
bind('accountCancel','click',async()=>{accountToken='';resetDialog.close();});
bind('accountForm','submit',async()=>{const form=$('accountForm');if(accountToken&&form.elements.password.value!==form.elements.confirm.value)throw new Error('Passwords do not match.');const result=await api(accountToken?'/api/account/complete':'/api/account/request',{method:'POST',body:accountToken?{token:accountToken,password:form.elements.password.value}:{email:form.elements.email.value}});const completed=!!accountToken;accountToken='';resetDialog.close();if(completed)signOutView('Password saved. Sign in with your username and new password.');else if(me)notify(result.message);else $('loginError').textContent=result.message;});
session().catch(()=>{$('login').hidden=false;$('shell').hidden=true;}).finally(()=>{if(accountToken)openAccount();});
setInterval(syncAccess,2000);
window.addEventListener('focus',syncAccess);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)syncAccess();});
window.addEventListener('offline',()=>{if(me)signOutView('Connection lost. Sign in again when connected.');});

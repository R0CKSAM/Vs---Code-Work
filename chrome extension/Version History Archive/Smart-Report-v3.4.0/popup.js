"use strict";
const $ = id => document.getElementById(id);
const FIELDS = ['dashboard', 'to', 'interval'];
let snapshot = {}, saveTimer = null, saveChain = Promise.resolve(), operationBusy = false, localError = '', dirty = false;
const EMAIL_MATCH = /[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+/g;
const extractEmails = value => (String(value || '').match(EMAIL_MATCH) || []);
function unique(items) { const seen = new Set(); return items.filter(email => { const key=email.toLowerCase(); if(seen.has(key))return false;seen.add(key);return true; }); }
const addresses = () => unique(extractEmails($('to').value));
const formatTime = time => time ? new Date(time).toLocaleString(undefined,{day:'numeric',month:'short',hour:'numeric',minute:'2-digit'}) : null;
function send(action, config, extra={}) { return new Promise((resolve,reject)=>chrome.runtime.sendMessage({action,config,...extra}, response=>{
  if(chrome.runtime.lastError)return reject(Error(chrome.runtime.lastError.message));
  if(!response)return reject(Error('Background extension did not respond. Reload the extension and retry.'));
  response.ok?resolve(response.result):reject(Error(response.error||'Request failed'));
})); }
function showStatus(str){$('status').textContent=str;}
function recipientUI(){
  const emails=addresses(), chipbox=$('recipientChips');
  $('recipientCount').textContent=emails.length+(emails.length===1?' email':' emails');
  chipbox.replaceChildren();
  for (const email of emails.slice(0,8)) { const s=document.createElement('span');s.className='chip';s.textContent=email;chipbox.append(s); }
  if(emails.length>8){const s=document.createElement('span');s.className='chip';s.textContent='+'+(emails.length-8)+' more';chipbox.append(s);}
}
function mergePaste(event){
  const paste=event.clipboardData?.getData('text/plain')||'';
  const incoming=unique(extractEmails(paste));if(!incoming.length)return;
  event.preventDefault();
  const existing=$('to').value.trim();
  // Preserve unfinished input and append unique complete addresses.
  const unfinished=existing.replace(EMAIL_MATCH,'').replace(/[,;\s<>]+/g,' ').trim();
  const merged=unique([...extractEmails(existing),...incoming]);
  $('to').value=(unfinished?unfinished+'\n':'')+merged.join(', ');
  markEdited();
}
function markEdited(){dirty=true;localError='';recipientUI();$('savedMessage').textContent='Saving…';clearTimeout(saveTimer);saveTimer=setTimeout(()=>persist().catch(e=>showError(e.message)),500);refreshVisualOnly();}
function form(){return {dashboard:$('dashboard').value.trim(),to:$('to').value.trim(),interval:$('interval').value.trim()===''?null:Number($('interval').value)};}
async function persist(){clearTimeout(saveTimer);const data=form();saveChain=saveChain.catch(()=>{}).then(()=>send('CONFIG',data));await saveChain;dirty=false;$('savedMessage').textContent='Saved';}
function showError(message){localError=message;$('errorBox').hidden=false;$('errorText').textContent=message;showStatus('Action failed: '+message);}
function refreshVisualOnly(){if(Object.keys(snapshot).length)render(snapshot,false);}
function updateEvents(events){const ul=$('activity');ul.replaceChildren();for(const event of (events||[]).slice(0,3)){
  const li=document.createElement('li');li.className=event.level==='error'?'bad':event.level==='success'?'good':'';
  const message=document.createElement('span');message.textContent=event.message.split('\n')[0];
  const time=document.createElement('time');time.textContent=formatTime(event.at)||'';li.append(message,time);ul.append(li);
}if(!ul.children.length){const li=document.createElement('li');li.textContent='No activity yet';ul.append(li);}}
function render(data, updateActivity=true){
  snapshot=data;const mode=data.mode||'stopped',run=data.runState||{},connected=!!data.connected;
  $('mode').textContent=run.busy?'Working…':mode==='running'?'Running':mode==='paused'?'Paused':'Stopped';
  $('modeLabel').textContent=run.busy?'Processing':mode==='running'?'Scheduled':mode==='paused'?'On hold':'Idle';
  $('modeBadge').className='status-pill '+(run.busy?'working':mode);
  $('dashboardReady').className=(data.lastCaptureAt && data.lastCaptureUrl===$('dashboard').value.trim())?'ready':'';
  $('outlookReady').className=(connected && data.verifiedAddress && Date.now()-data.verifiedAt<60*60*1000)?'ready':'';
  $('recipientReady').className=addresses().length?'ready':'';
  $('authStatus').textContent=connected?(data.verifiedAddress||'Account connected'):'Not connected';
  $('signIn').hidden=connected;$('signOut').hidden=!connected;
  $('stage').textContent=run.stage||(mode==='running'?'Waiting for next report':'No active report');
  const pct=run.busy?Math.max(0,Math.min(99,run.percent||0)):(run.percent===100?100:0);
  $('bar').style.width=pct+'%';$('progressTrack').setAttribute('aria-valuenow',String(pct));$('percent').textContent=run.busy?pct+'%':'';
  $('nextRun').textContent=formatTime(data.nextRun)||(mode==='paused'?'Paused':'—');
  $('lastSent').textContent=formatTime(data.lastSent)||'Never';$('sent').textContent=String(data.sent||0);
  $('start').hidden=mode==='running';$('pauseResume').hidden=mode==='stopped';$('stop').hidden=mode==='stopped';
  $('pauseResume').textContent=mode==='paused'?'Resume':'Pause';
  ['start','pauseResume','stop','test','signIn','signOut','capture','openTab','verify'].forEach(id=>$(id).disabled=operationBusy);
  $('test').disabled=operationBusy||!connected;
  const error=localError||run.error||data.lastError||'';
  $('errorBox').hidden=!error;$('errorText').textContent=error;
  $('policyNote').textContent='Recipients must use your company Outlook email domain unless explicitly allowed by your administrator.';
  if(updateActivity)updateEvents(data.events);
  if(!operationBusy)showStatus(error?'Problem detected — see Report issue above.':run.busy?'Preparing your report…':(data.lastStatus||'Send a test before you start scheduled reporting.'));
}
async function refresh(){const result=await send('GET');render(result);}
async function perform(action, options={}){
  if(operationBusy)return;
  operationBusy=true;localError='';refreshVisualOnly();
  try{
    if(options.save)await persist();
    if(options.confirm){const list=addresses().join('\n');if(!confirm(options.confirm+'\n\nSend to:\n'+(list||'(none)')))return;}
    showStatus(options.working||'Working…');
    const result=await send(action,undefined,options.extra);
    if(action==='USE_TAB'){$('dashboard').value=result.url;await persist();}
    if(action==='CAPTURE'&&result.preview){$('preview').src=result.preview;$('previewwrap').hidden=false;$('previewmeta').textContent='Screenshot ready. Check that all Grafana panels appear.';}
    if(action==='VERIFY')showStatus('Outlook verified: '+result.address);
    if(action==='LOGIN')showStatus('Outlook connected: '+result.address);
    if(action==='TEST')showStatus('Outlook accepted the test email. Check your inbox.');
    await refresh();
  }catch(e){showError(e.message);}
  finally{operationBusy=false;refreshVisualOnly();}
}
for(const id of FIELDS)$(id).addEventListener('input',markEdited);
$('to').addEventListener('paste',mergePaste);
$('signIn').onclick=()=>perform('LOGIN',{working:'Connecting to Microsoft Outlook…'});
$('signOut').onclick=()=>{if(confirm('Disconnect Outlook and pause reports?'))perform('LOGOUT');};
$('useTab').onclick=async()=>{try{const [tab]=await chrome.tabs.query({active:true,currentWindow:true});if(!tab?.id)throw Error('Open the Grafana tab first.');perform('USE_TAB',{extra:{tabId:tab.id,url:tab.url}});}catch(e){showError(e.message);}};
$('openTab').onclick=()=>perform('OPEN_TAB',{save:true});
$('verify').onclick=()=>perform('VERIFY',{working:'Checking Outlook connection…'});
$('capture').onclick=()=>perform('CAPTURE',{save:true,working:'Checking dashboard screenshot…'});
$('test').onclick=()=>perform('TEST',{save:true,confirm:'Send a single test screenshot?',working:'Taking screenshot and sending email…'});
$('start').onclick=()=>perform('START',{save:true,confirm:'Start automatic reports every '+$('interval').value+' minute(s)?'});
$('pauseResume').onclick=()=>perform(snapshot.mode==='paused'?'RESUME':'PAUSE',{save:true});
$('stop').onclick=()=>perform('STOP');
$('export').onclick=async()=>{try{const r=await send('LOGS');const blob=new Blob([JSON.stringify({app:'Smart Report v3.4',exportedAt:new Date().toISOString(),events:r.logs},null,2)],{type:'application/json'});const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='smart-report-logs-'+new Date().toISOString().slice(0,10)+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(e){showError(e.message);}};
chrome.storage.onChanged.addListener((_changes,area)=>{if(area==='local')refresh().catch(()=>{});});
(async()=>{const data=await send('GET');$('dashboard').value=data.config?.dashboard||'';$('to').value=data.config?.to||'';$('interval').value=(Number(data.config?.interval)>0?data.config.interval:15);recipientUI();render(data);if(data.connected){send('VERIFY').then(()=>refresh()).catch(e=>{showError(e.message);});}})().catch(e=>showError('Extension unavailable: '+e.message));

"use strict";
const $=id=>document.getElementById(id);
let snapshot={},view='',operationBusy=false,dirty=false,revision=0,saveTimer,toastTimer,saveChain=Promise.resolve(),localError='',initialized=false;
let googleSession={checked:false,active:false,needsReconnect:false,address:'',error:''};
const fields=['dashboard','to','cc','bcc','interval','rowMode','sender','subject'];
const time=t=>t?new Date(t).toLocaleString(undefined,{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'}):'';
function send(action,config,extra={}){return new Promise((resolve,reject)=>chrome.runtime.sendMessage({action,config,...extra},r=>{if(chrome.runtime.lastError)return reject(Error(chrome.runtime.lastError.message));if(!r?.ok)return reject(Error(r?.error||'Extension did not respond. Reload it and retry.'));resolve(r.result);}));}
function recipients(){
 const parse=raw=>String(raw||'').replace(/(?:"[^"\n]+"|[^,;\n<>]+)\s*<\s*([^<>\s]+@[^<>\s]+)\s*>/g,'$1').split(/[,;\s]+/).filter(Boolean).map(x=>x.toLowerCase());
 const seen=new Set(),groups={};
 for(const key of ['to','cc','bcc'])groups[key]=parse($(key).value).filter(x=>{if(seen.has(x))return false;seen.add(x);return true;});
 const all=[...groups.to,...groups.cc,...groups.bcc];const domains=snapshot.allowedDomains||[];
 const invalid=all.find(x=>!/^\S+@[^\s@<>]+\.[^\s@<>]+$/.test(x)||(domains.length&&!domains.includes(x.split('@')[1])));
 return {all,groups,error:invalid?'Check this address or its allowed domain: '+invalid:all.length>50?'Use no more than 50 recipients.':groups.to.length===0?'At least one To address is required.':''};
}
function recipientUI(){const r=recipients();$('recipientCount').textContent=r.all.length+' recipient'+(r.all.length===1?'':'s');$('recipientError').textContent=r.error;$('recipientError').hidden=!r.error;for(const key of ['to','cc','bcc'])$(key).setAttribute('aria-invalid',String(!!r.error));}
function form(){return {dashboard:$('dashboard').value.trim(),to:$('to').value.trim(),cc:$('cc').value.trim(),bcc:$('bcc').value.trim(),interval:Number($('interval').value),expandRows:$('rowMode').value==='all',sender:$('sender').value,subject:$('subject').value.trim()};}
function validDelivery(){const r=recipients(),n=Number($('interval').value);return r.all.length>0&&!r.error&&Number.isInteger(n)&&n>=1&&n<=1440;}
function toast(message){clearTimeout(toastTimer);$('toastText').textContent=message;$('toast').hidden=false;toastTimer=setTimeout(()=>$('toast').hidden=true,7000);}
function showError(message){localError=message;$('errorText').textContent=message;$('errorBox').hidden=false;}
function refreshVisualOnly(){if(initialized)render(snapshot);}
function markEdited(){dirty=true;revision++;localError='';$('savedMessage').textContent='Saving…';clearTimeout(saveTimer);saveTimer=setTimeout(()=>persist().catch(e=>showError(e.message)),600);refreshVisualOnly();}
async function persist(){clearTimeout(saveTimer);const version=revision,data=form();saveChain=saveChain.catch(()=>{}).then(()=>send('CONFIG',data));await saveChain;if(version===revision){dirty=false;$('savedMessage').textContent='Saved automatically';}await refresh();}
function render(data){
 snapshot=data;initialized=true;
 const connected=!!data.connected,outlookConnected=!!data.outlookConnected,googleConnected=!!data.googleAddress,mode=data.mode||'stopped',run=data.runState||{},busy=operationBusy||!!run.busy,ready=!!data.approvedPreview&&validDelivery();
 const gmailReady=googleConnected&&googleSession.checked&&googleSession.active&&!googleSession.needsReconnect;
 const sender=$('sender').value||data.config?.sender||'outlook';const senderConnected=sender==='gmail'?gmailReady:outlookConnected;
 const gmailScheduleReady=gmailReady&&data.gmailScheduleTested;
 $('loading').hidden=true;$('signInView').hidden=connected;$('appView').hidden=!connected;$('accountMenu').hidden=!connected;
 $('outlookConnectionState').textContent=outlookConnected?(data.verifiedAddress||'Connected'):'Not connected';
 $('googleConnectionState').textContent=googleConnected?(googleSession.needsReconnect?'Reconnect needed':data.googleAddress):'Not connected';
 $('connectOutlook').hidden=outlookConnected;$('connectOutlook').disabled=busy;
 $('googleVerify').textContent=googleConnected?(googleSession.needsReconnect?'Reconnect':googleSession.active?'Connected':'Checking…'):'Connect';$('googleVerify').disabled=busy||(googleConnected&&!googleSession.needsReconnect);
 $('googleSignOut').hidden=!googleConnected;$('googleSignOut').disabled=busy;
 $('providerNotice').hidden=!googleSession.needsReconnect;$('providerNotice').textContent=googleSession.needsReconnect?'Google authorization needs renewal. Click Reconnect in the account row. Your dashboard settings are preserved.':'';
 $('googleTools').hidden=!googleConnected;$('googleStatus').textContent=googleConnected?(gmailReady?'Sending as '+data.googleAddress:'Reconnect Gmail to send'):'Connect Google to test Gmail.';
 $('googleTest').disabled=!gmailReady||!ready||busy||dirty||mode==='running'||!!data.gmailSubmissionPending;
 $('gmailRecovery').hidden=!data.gmailSubmissionPending;$('clearGmailPending').disabled=busy;
 $('outlookRecovery').hidden=!data.outlookSubmissionPending;$('clearOutlookPending').disabled=busy;
 if(!connected){view='';$('accountMenu').open=false;}
 let selected=view||(!data.approvedPreview?'dashboard':!validDelivery()?'delivery':'overview');
 if(selected==='overview'&&!ready)selected=data.approvedPreview?'delivery':'dashboard';
 for(const name of ['dashboard','delivery','overview'])$(name+'View').hidden=selected!==name;
 $('stepper').hidden=selected==='overview';
 ['dashboard','delivery','ready'].forEach((name,i)=>{const index=['dashboard','delivery','overview'].indexOf(selected);$(name+'Step').className=i===index?'active':i<index?'done':'';});
 $('authStatus').textContent=outlookConnected?(data.verifiedAddress||'Outlook connected'):(data.googleAddress||'Gmail connected');
 $('signIn').disabled=busy;$('signIn').textContent=operationBusy?'Connecting…':'Sign in with Microsoft';
 $('signOut').hidden=!outlookConnected;$('verify').hidden=!outlookConnected;$('signOut').disabled=busy;$('verify').disabled=busy;
 $('linkedDashboard').textContent=$('dashboard').value?'Dashboard linked. Review the screenshot below.':'No dashboard linked yet.';
 $('rowHelp').textContent=$('rowMode').value==='all'?'All recognized channel rows will be opened for each report.':'Open the rows you want in Grafana. Future reports use the tab’s layout; row selections are not saved.';
 $('capture').disabled=busy||!$('dashboard').value.trim();
 $('useTab').disabled=busy;$('openTab').disabled=busy||!$('dashboard').value.trim();
 $('viewPreview').hidden=!data.lastCaptureMeta;
 $('continueDashboard').hidden=!data.approvedPreview;$('continueDashboard').disabled=busy||dirty;
 $('approvalHint').textContent=data.approvedPreview?'Screenshot approved. Continue to delivery.':'Check the screenshot, then approve it in the preview tab.';
 $('approvalHint').className='notice'+(data.approvedPreview?' ready':'');
 $('dashboardBack').hidden=!ready;
 $('captureProgress').hidden=!run.busy;
 $('stage').textContent=run.stage||'Preparing screenshot';$('percent').textContent=(run.percent||0)+'%';
 $('bar').style.width=Math.min(100,run.percent||0)+'%';$('progressTrack').setAttribute('aria-valuenow',String(run.percent||0));
 recipientUI();$('policyNote').textContent=data.allowExternalRecipients?'External recipients permitted. Confirm every address before sharing internal Grafana data.':data.allowedDomains?.length?'Allowed domains: '+data.allowedDomains.join(', '):'Recipients are subject to the company sender-domain policy.';
 const n=Number($('interval').value);$('interval').setAttribute('aria-invalid',String(!Number.isInteger(n)||n<1||n>1440));
 $('continueDelivery').disabled=busy||!validDelivery();
 for(const id of fields)$(id).disabled=!!run.busy;
 $('mode').textContent=run.busy?(data.lastMailOutcome==='submitting'?'Sending your report':'Preparing your report'):mode==='running'?'Automatic emails are on':mode==='paused'?'Your schedule is paused':'Ready when you are';
 $('modeLabel').textContent=run.busy?'In progress':mode==='running'?'Active':mode==='paused'?'Paused':'Ready';
 $('modeBadge').className='status-pill '+(run.busy?'working':mode);
 $('scheduleSummary').textContent=run.busy?run.stage:mode==='running'?'A fresh screenshot via '+(sender==='gmail'?'Gmail':'Outlook')+' every '+data.config.interval+' minutes.':mode==='paused'?'Settings are saved. Resume when you’re ready.':sender==='gmail'&&!gmailScheduleReady?'Send an approved Gmail test first, then activate scheduling.':'Send a test first, then turn on your schedule.';
 $('nextReportCard').hidden=!(outlookConnected||googleConnected);
 $('nextRun').textContent=mode==='running'?(time(data.nextRun)||'Checking schedule…'):mode==='paused'?'Paused':'Not scheduled';
 $('countdown').textContent=mode==='running'&&data.nextRun?(data.nextRun>Date.now()?'In '+Math.ceil((data.nextRun-Date.now())/60000)+' min':'Due now · may be delayed'):'';
 $('elapsed').textContent=run.busy?Math.floor((Date.now()-run.startedAt)/1000)+'s elapsed':'';
 $('nextAction').textContent=run.busy?'You can close this popup. Keep Chrome and Grafana open.':mode==='running'?'You’re all set. Screenshot preparation happens before each email.':mode==='paused'?'Resume starts the next report after one full interval.':'Check your test email’s attachment before starting automatic reports.';
 $('summaryRecipients').textContent=recipients().all.join(', ');$('summaryInterval').textContent='Every '+n+' minutes';$('summarySender').textContent=sender==='gmail'?'Google Gmail':'Microsoft Outlook';$('summaryCapture').textContent=data.approvedPreview?'Reviewed & approved':'Review required';
 $('start').hidden=mode!=='stopped';$('pauseResume').hidden=mode==='stopped';$('pauseResume').textContent=mode==='running'?'Pause automatic emails':'Resume automatic emails';$('pauseResume').dataset.controlMode=mode;
 $('outlookTestRow').hidden=!outlookConnected;$('frequencyRow').hidden=false;$('lastOutlookRow').hidden=!(outlookConnected||googleConnected);
 $('start').disabled=busy||dirty||!ready||!senderConnected||(sender==='gmail'&&!gmailScheduleReady)||(sender==='outlook'&&data.outlookSubmissionPending);$('pauseResume').disabled=busy||dirty||!ready||!senderConnected||(sender==='gmail'&&!gmailScheduleReady)||(sender==='outlook'&&data.outlookSubmissionPending);$('test').disabled=busy||dirty||!ready||!outlookConnected||mode==='running';$('test').hidden=!outlookConnected;
 $('stop').hidden=mode==='stopped';$('stop').disabled=false;
 $('editDashboard').disabled=busy;$('editDelivery').disabled=busy;
 const last=data.lastCompletedMail;
 $('lastMailOutcome').textContent=last?(last.outcome==='accepted'?'Accepted by '+(last.provider==='gmail'?'Gmail':'Outlook'):'Failed / unconfirmed'):'None yet';
 $('gmailLastResult').textContent=data.gmailLastOutcome==='accepted'&&data.gmailLastSent?'Gmail test accepted '+time(data.gmailLastSent)+' · '+(data.gmailScheduleTested?'Ready for scheduled Gmail sending with these recipients.':'If recipients changed, send another test.'):'To schedule with Gmail, first send an approved test message.';
 $('lastMailOutcome').className=last?.outcome==='accepted'?'mail-ok':last?'mail-error':'';
 $('lastMailTime').textContent=last?time(last.at):'';$('sent').textContent=data.sent||0;$('failed').textContent=data.failedMail||0;
 const error=localError||(connected&&!run.busy?(data.lastError||run.error||''):'');
 $('errorBox').hidden=!error;$('errorText').textContent=error;
 $('activity').replaceChildren();
 for(const e of data.events||[]){const li=document.createElement('li'),s=document.createElement('span'),t=document.createElement('time');s.textContent=e.message.split('\n')[0];t.textContent=time(e.at);li.className=e.level==='error'?'bad':e.level==='success'?'good':'';li.append(s,t);$('activity').append(li);}
 if(!data.events?.length){const li=document.createElement('li');li.textContent='No activity yet';$('activity').append(li);}
 $('status').textContent=run.busy?run.stage:'';
}
async function refresh(){const data=await send('GET');if(!initialized){$('dashboard').value=data.config?.dashboard||'';$('to').value=data.config?.to||'';$('cc').value=data.config?.cc||'';$('bcc').value=data.config?.bcc||'';$('interval').value=data.config?.interval||15;$('rowMode').value=data.config?.expandRows===false?'current':'all';$('sender').value=data.config?.sender||'outlook';$('subject').value=data.config?.subject||'Grafana Dashboard Report · {time}';}render(data);}
function confirmAction(title,body,label){return new Promise(resolve=>{const dialog=$('confirmDialog');const previous=document.activeElement;$('confirmTitle').textContent=title;$('confirmBody').textContent=body;$('confirmAccept').textContent=label;function finish(value){dialog.close();previous?.focus();resolve(value);}$('confirmAccept').onclick=()=>finish(true);$('confirmCancel').onclick=()=>finish(false);dialog.oncancel=e=>{e.preventDefault();finish(false);};dialog.showModal();$('confirmCancel').focus();});}
async function perform(action,{save=false,extra={},confirmation=null}={}){
 if(operationBusy)return;
 if(confirmation&&!await confirmAction(...confirmation))return;
 operationBusy=true;localError='';$('accountMenu').open=false;refreshVisualOnly();
 try{
  if(save)await persist();
  const result=await send(action,undefined,extra);
  if(action==='USE_TAB'){$('dashboard').value=result.url;await persist();}
  if(action==='LOGOUT'){view='';$('toast').hidden=true;}
  await refresh();
  const messages={LOGIN:'Signed in. Let’s set up your report.',LOGOUT:'Signed out. Automatic emails are paused.',USE_TAB:'Dashboard linked. Check the screenshot next.',CAPTURE:'Preview ready. Review and approve it in the new tab.',VERIFY:'Outlook connection verified.',TEST:'Outlook accepted your test. Check the received attachment.',START:'Schedule started. The first report begins after one interval.',RESUME:'Schedule resumed.',PAUSE:'Automatic emails paused.',STOP:'Schedule stopped. Your settings are saved.'};
  if(messages[action])toast(messages[action]);
 }catch(e){showError(e.message);}finally{operationBusy=false;refreshVisualOnly();}
}
fields.forEach(id=>$(id).addEventListener('input',markEdited));
async function refreshGoogle(){try{const g=await send('GOOGLE_STATUS');googleSession={checked:true,active:!!g.active,needsReconnect:!!g.needsReconnect,address:g.address||'',error:g.error||''};$('googleState').textContent=g.configured?'':'Google OAuth setup required; see GOOGLE-SETUP.md.';refreshVisualOnly();}catch(e){googleSession={checked:true,active:false,needsReconnect:true,address:'',error:e.message};$('googleState').textContent=e.message;refreshVisualOnly();}}
$('googleSignIn').onclick=async()=>{if(operationBusy)return;operationBusy=true;try{const r=await send('GOOGLE_LOGIN');toast('Google authorized: '+r.address);await refresh();await refreshGoogle();view='dashboard';refreshVisualOnly();}catch(e){showError(e.message);}finally{operationBusy=false;refreshVisualOnly();}};
$('googleVerify').onclick=async()=>{if(operationBusy)return;operationBusy=true;try{const r=await send('GOOGLE_LOGIN');toast('Gmail connected: '+r.address);await refresh();await refreshGoogle();}catch(e){showError(e.message);}finally{operationBusy=false;refreshVisualOnly();}};
$('connectOutlook').onclick=()=>perform('LOGIN');
$('googleSignOut').onclick=async()=>{if(operationBusy)return;if(!await confirmAction('Disconnect Gmail?','This disconnects only Gmail. Any active Outlook schedule will remain unchanged.','Disconnect'))return;operationBusy=true;try{await send('GOOGLE_LOGOUT');googleSession={checked:true,active:false,needsReconnect:false,address:'',error:''};await refresh();toast('Gmail disconnected.');}catch(e){showError(e.message);}finally{operationBusy=false;refreshVisualOnly();}};
$('googleTest').onclick=async()=>{if(operationBusy)return;operationBusy=true;try{await persist();if(!await confirmAction('Send Gmail test?', 'Send the last approved Grafana screenshot through the connected Gmail account to: '+recipients().all.join(', ')+'. This is one email; if accepted it unlocks scheduled Gmail sending for these settings.','Send test'))return;const r=await send('GOOGLE_TEST');toast(r.message);await refresh();}catch(e){showError(e.message);}finally{operationBusy=false;refreshVisualOnly();}};
$('clearOutlookPending').onclick=async()=>{if(operationBusy)return;if(!await confirmAction('Confirm Outlook Sent Items checked','Check the sender’s Outlook Sent Items for the possibly delivered report before clearing the blocker. This does not unsend or delete an email.','Clear blocker'))return;try{await send('OUTLOOK_CLEAR_PENDING');await refresh();toast('Outlook send blocker cleared.');}catch(e){showError(e.message);}};
$('clearGmailPending').onclick=async()=>{if(operationBusy)return;if(!await confirmAction('Confirm Gmail Sent Items checked','Clear the uncertain-send blocker ONLY after you have checked the connected Gmail account’s Sent folder for this report. This does not retract a sent message.','Clear blocker'))return;try{await send('GOOGLE_CLEAR_PENDING');await refresh();toast('Gmail send blocker cleared.');}catch(e){showError(e.message);}};
$('signIn').onclick=()=>perform('LOGIN');
$('signOut').onclick=()=>perform('LOGOUT',{confirmation:['Sign out of Outlook?','Automatic reports will pause. Your dashboard and delivery settings will stay saved. Your Gmail connection remains available.','Sign out']});
$('verify').onclick=()=>perform('VERIFY');
$('useTab').onclick=async()=>{try{const [tab]=await chrome.tabs.query({active:true,currentWindow:true});if(!tab?.id)throw Error('Open your Grafana dashboard first.');await perform('USE_TAB',{extra:{tabId:tab.id,url:tab.url}});}catch(e){showError(e.message);}};
$('capture').onclick=()=>perform('CAPTURE',{save:true});
$('viewPreview').onclick=()=>chrome.tabs.create({url:chrome.runtime.getURL('preview.html')}).catch(e=>showError(e.message));
$('openTab').onclick=()=>perform('OPEN_TAB',{save:true});
$('continueDashboard').onclick=()=>{view='delivery';refreshVisualOnly();$('to').focus();};
$('continueDelivery').onclick=async()=>{try{await persist();view='overview';refreshVisualOnly();toast('Delivery settings saved. You’re ready to send a test.');}catch(e){showError(e.message);}};
$('deliveryBack').onclick=()=>{view=snapshot.approvedPreview&&validDelivery()?'overview':'dashboard';refreshVisualOnly();};
$('dashboardBack').onclick=()=>{view='overview';refreshVisualOnly();};
$('editDashboard').onclick=()=>{view='dashboard';refreshVisualOnly();};
$('editDelivery').onclick=()=>{view='delivery';refreshVisualOnly();};
$('test').onclick=()=>perform('TEST',{save:true,confirmation:['Send a test email?','Send one fresh screenshot to:\n'+recipients().all.join('\n')+'\n\nThis does not start automatic emails.','Send test']});
$('start').onclick=()=>perform('START',{save:true,confirmation:['Start automatic emails?','Send from '+($('sender').value==='gmail'?'Gmail':'Outlook')+' to '+recipients().all.join(', ')+' every '+$('interval').value+' minutes.\n\nConfirm each recipient is authorized to receive these internal analytics. The first report starts after one full interval.','Start schedule']});
async function interrupt(action){try{await send(action);await refresh();toast(action==='STOP'?'Schedule stopped. Settings are saved.':'Automatic emails paused.');}catch(e){showError(e.message);}}
$('pauseResume').onclick=()=>snapshot.mode==='running'?interrupt('PAUSE'):perform('RESUME',{save:true});
$('stop').onclick=()=>interrupt('STOP');
$('dismissToast').onclick=()=>{clearTimeout(toastTimer);$('toast').hidden=true;};
document.addEventListener('click',e=>{if(!$('accountMenu').contains(e.target))$('accountMenu').open=false;});
document.addEventListener('keydown',e=>{if(e.key==='Escape'){$('accountMenu').open=false;$('toast').hidden=true;}});
$('export').onclick=async()=>{try{const r=await send('LOGS'),url=URL.createObjectURL(new Blob([JSON.stringify({app:'Smart Report',events:r.logs},null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='smart-report-logs.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast('Logs exported. They may contain internal dashboard details.');}catch(e){showError(e.message);}};
chrome.storage.onChanged.addListener((_changes,area)=>{if(area==='local')refresh().catch(e=>showError(e.message));});
refresh().then(refreshGoogle).catch(e=>{$('loading').hidden=true;$('signInView').hidden=false;showError(e.message);});
setInterval(()=>{if(initialized&&snapshot.connected)refreshVisualOnly();},1000);
setInterval(()=>{if(initialized&&snapshot.connected)refresh().catch(()=>{});},15000);

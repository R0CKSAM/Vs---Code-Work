"use strict";
const $ = id => document.getElementById(id);
const FIELDS = ['dashboard', 'to', 'cc', 'bcc', 'subject', 'interval', 'settle'];
const DEFAULTS = { dashboard: '', to: '', cc: '', bcc: '', subject: 'Grafana Dashboard Report · {time}', interval: 15, settle: 12 };
let snapshot = {}, pendingSave = null, saveChain = Promise.resolve(), operationBusy = false, localError = '';
const EMAIL_MATCH = /[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+/g;
const extractEmails = value => (String(value || '').match(EMAIL_MATCH) || []);
const uniqueAddresses = entries => {
  const found = new Set(), result = [];
  for (const entry of entries) {
    const key = entry.toLowerCase();
    if (!found.has(key)) { found.add(key); result.push(entry); }
  }
  return result;
};
const countAddresses = () => uniqueAddresses(['to', 'cc', 'bcc'].flatMap(k => extractEmails($(k).value))).length;
const friendlyTime = value => value ? new Date(value).toLocaleString(undefined, { day:'numeric', month:'short', hour:'numeric', minute:'2-digit' }) : null;
function setStatus(message) { $('status').textContent = message; }
function readForm() {
  return Object.fromEntries(FIELDS.map(k => [k, (k === 'interval' || k === 'settle') ? Number($(k).value) : $(k).value.trim()]));
}
function request(action, config, extra) {
  return new Promise((resolve, reject) => chrome.runtime.sendMessage({ action, config, ...(extra || {}) }, response => {
    if (chrome.runtime.lastError) return reject(Error(chrome.runtime.lastError.message));
    if (!response) return reject(Error('Background worker did not respond'));
    response.ok ? resolve(response.result) : reject(Error(response.error || 'Request failed'));
  }));
}
function updateRecipientCounter() {
  const n = countAddresses();
  $('recipientCount').textContent = n + (n === 1 ? ' address' : ' addresses');
}
function pasteEmails(event) {
  const raw = event.clipboardData?.getData('text/plain') || '';
  const incoming = uniqueAddresses(extractEmails(raw));
  if (!incoming.length) return;
  event.preventDefault();
  const field = event.currentTarget, previous = field.value.trim();
  // Merge instead of replacing current entries. Preserve unfinished typed text
  // instead of silently erasing it while cleaning a pasted Outlook list.
  const simpleList = previous === '' || /^(\s*[^\s,;<>]+@[^\s,;<>]+\.[^\s,;<>]+\s*[,;\s]*)+$/.test(previous);
  field.value = simpleList
    ? uniqueAddresses([...extractEmails(previous), ...incoming]).join(', ')
    : [previous.replace(/[,;\s]+$/, ''), ...incoming].filter(Boolean).join(', ');
  updateRecipientCounter();
  queueAutosave();
}
function queueAutosave() {
  clearTimeout(pendingSave);
  $('savedMessage').textContent = 'Editing…';
  pendingSave = setTimeout(() => { persist().catch(err => setStatus('Could not save: ' + err.message)); }, 550);
}
function persist() {
  clearTimeout(pendingSave);
  const form = readForm();
  saveChain = saveChain.catch(() => {}).then(() => request('CONFIG', form));
  $('savedMessage').textContent = 'Saving…';
  return saveChain.then(() => { $('savedMessage').textContent = 'Saved'; });
}
function hydrate(form) {
  for (const k of FIELDS) $(k).value = form?.[k] ?? DEFAULTS[k];
  updateRecipientCounter();
}
function renderActivity(events) {
  const activity = $('activity');
  activity.replaceChildren();
  if (!(events || []).length) {
    const li = document.createElement('li'), dot = document.createElement('span'), text = document.createElement('span');
    dot.className='activity-marker'; text.textContent='No activity yet'; li.append(dot,text); activity.append(li); return;
  }
  for (const entry of events.slice(0, 3)) {
    const li=document.createElement('li'),dot=document.createElement('span'),details=document.createElement('div'),time=document.createElement('time');
    dot.className='activity-marker '+(entry.level==='error'?'error':entry.level==='success'?'success':'info');
    details.className='activity-content';details.textContent=entry.message;
    time.textContent=friendlyTime(entry.at) || '';
    details.append(time); li.append(dot,details); activity.append(li);
  }
}
function render(data) {
  snapshot = data;
  const mode = data.mode || 'stopped', run = data.runState || {};
  const connected = !!data.connected;
  $('mode').textContent = mode === 'running' ? 'Running' : mode === 'paused' ? 'Paused' : 'Stopped';
  $('modeLabel').textContent = run.busy ? 'Working' : mode === 'running' ? 'Scheduled' : mode === 'paused' ? 'Paused' : 'Idle';
  $('modeBadge').className='mode-pill ' + mode;
  $('authStatus').textContent = connected ? 'Connected and ready to send' : data.companyConfigured ? 'Sign in to your work account' : 'Microsoft IDs need setup';
  $('authStatus').classList.toggle('connected',connected);
  $('signIn').hidden = connected; $('signOut').hidden = !connected;
  for (const [id,ready] of [['dashboardReady', /^https:\/\/grafana-apj\.trafficpeak\.live\/d\//.test($('dashboard').value.trim())], ['outlookReady', connected], ['recipientReady', countAddresses()>0]]) {
    $(id).classList.toggle('good',ready);
  }
  const stage = run.stage || (mode === 'running' ? 'Waiting for next scheduled report' : 'No report in progress');
  $('stage').textContent = stage;
  const percent = run.busy ? Math.max(0,Math.min(99,run.percent || 0)) : run.percent === 100 ? 100 : 0;
  $('percent').textContent = run.busy ? percent + '%' : '';
  $('bar').style.width = percent + '%';
  $('progressTrack').setAttribute('aria-valuenow',String(percent));
  $('nextRun').textContent = friendlyTime(data.nextRun) || (mode==='paused' ? 'On hold' : 'Not scheduled');
  $('lastSent').textContent = friendlyTime(data.lastSent) || 'Never';
  $('sent').textContent = String(data.sent || 0);
  $('pauseResume').textContent = mode==='paused' ? 'Resume' : 'Pause';
  $('pauseResume').disabled = operationBusy || mode==='stopped';
  $('stop').disabled = operationBusy || mode==='stopped';
  $('start').disabled = operationBusy || mode==='running';
  $('test').disabled = operationBusy || !connected;
  $('signIn').disabled = operationBusy || connected;
  $('signOut').disabled = operationBusy || !connected;
  const error = localError || run.error || data.lastError || '';
  $('errorBox').hidden = !error; $('errorText').textContent = error;
  const domains = (data.allowedDomains || []);
  $('policyNote').textContent = domains.length ? 'Allowed recipient domains: ' + domains.join(', ') : 'Security: sends are limited to your signed-in Outlook email domain unless IT explicitly allows other domains.';
  $('redirect').textContent = 'Microsoft redirect: ' + (data.redirect || '');
  if (data.events) renderActivity(data.events);
  if (!operationBusy) setStatus(error ? 'Issue: ' + error : run.busy ? 'A report is being prepared. Progress updates appear above.' : (data.lastStatus || 'Configure the report and start monitoring.'));
}
async function refresh() { render(await request('GET')); }
async function perform(fn) {
  if (operationBusy) return;
  operationBusy=true; localError=''; render(snapshot);
  try { await fn(); await refresh(); }
  catch(err) { localError=err.message; setStatus('Error: ' + err.message); }
  finally { operationBusy=false;render(snapshot); }
}
for (const id of FIELDS) {
  $(id).addEventListener('input', () => { localError=''; if (['to','cc','bcc'].includes(id)) updateRecipientCounter(); queueAutosave(); render(snapshot); });
}
for (const id of ['to','cc','bcc']) $(id).addEventListener('paste', pasteEmails);
$('useTab').onclick = () => perform(async () => {
  const [tab] = await chrome.tabs.query({ active:true,currentWindow:true });
  if (!tab?.id || !tab.url) throw Error('Open Grafana, then click the extension from that tab.');
  const result = await request('USE_TAB',undefined,{tabId:tab.id,url:tab.url});
  $('dashboard').value = result.url; await persist();
});
$('openTab').onclick = () => perform(async () => { await persist(); await request('OPEN_TAB'); });
$('signIn').onclick = () => perform(async () => { setStatus('Opening Microsoft sign-in…'); await request('LOGIN'); });
$('signOut').onclick = () => perform(async () => {
  if (!confirm('Disconnect Outlook and pause scheduled reports?')) return;
  await request('LOGOUT');
});
$('start').onclick = () => perform(async () => {
  await persist();
  if (!confirm(`Start sending one report every ${$('interval').value} minute(s) to ${countAddresses()} recipient(s)?`)) return;
  await request('START');
});
$('pauseResume').onclick = () => perform(async () => { await persist(); await request(snapshot.mode==='paused'?'RESUME':'PAUSE'); });
$('stop').onclick = () => perform(async () => { await request('STOP'); });
$('test').onclick = () => perform(async () => {
  await persist();
  if (!confirm(`Send one test report to ${countAddresses()} recipient(s)?`)) return;
  setStatus('Capturing Grafana and sending a test email…');
  const result=await request('TEST'); setStatus(result.message);
});
$('capture').onclick = () => perform(async () => {
  await persist(); setStatus('Capturing screenshot preview…');
  const result=await request('CAPTURE');
  $('preview').src=result.preview; $('previewwrap').hidden=false;
  $('previewmeta').textContent='Preview captured at 1600 × 900.';
});
$('export').onclick = () => perform(async () => {
  const result=await request('LOGS');
  const blob=new Blob([JSON.stringify({app:'Smart Report v3.3',exportedAt:new Date().toISOString(),events:result.logs},null,2)],{type:'application/json'});
  const url=URL.createObjectURL(blob), a=document.createElement('a');
  a.href=url; a.download='smart-report-logs-'+new Date().toISOString().slice(0,10)+'.json';a.click();
  setTimeout(()=>URL.revokeObjectURL(url),2000);
});
chrome.storage.onChanged.addListener((_changes,area) => { if (area==='local') refresh().catch(() => {}); });
(async () => {
  const data=await request('GET');hydrate(data.config);render(data);
})().catch(err=>setStatus('Extension unavailable: '+err.message));

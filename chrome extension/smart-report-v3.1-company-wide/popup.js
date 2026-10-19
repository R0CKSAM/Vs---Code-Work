"use strict";
const $=x=>document.getElementById(x);const ids=['dashboard','to','cc','bcc','subject','interval','settle'];let lastPreview=null;
function status(t){$('status').textContent=t;}
function request(action,config){return new Promise((resolve,reject)=>{chrome.runtime.sendMessage({action,config},r=>{if(chrome.runtime.lastError)return reject(Error(chrome.runtime.lastError.message));if(!r)return reject(Error('No response from background worker'));r.ok?resolve(r.result):reject(Error(r.error));});});}
async function refresh(){const d=await request('GET');for(const key of ids)if(document.activeElement!==$(key))$(key).value=d.config?.[key]??(key==='interval'?'15':key==='settle'?'12':key==='subject'?'Grafana Dashboard Report · {time}':'');$('authStatus').textContent=!d.companyConfigured?'Company IDs need setup':d.connected?'Session available':'Sign-in required';$('mode').textContent=(d.mode||'stopped').toUpperCase();$('count').textContent=(d.sent||0)+' emails accepted';$('scheduleInfo').textContent=d.nextRun?'Next attempt: '+new Date(d.nextRun).toLocaleString():d.lastSent?'Last sent: '+new Date(d.lastSent).toLocaleString():'Not scheduled';$('bar').style.width=d.mode==='running'?'100%':'0%';$('redirect').textContent='Microsoft redirect: '+d.redirect;status(d.lastError?'Latest issue: '+d.lastError:(d.lastStatus||'Ready.'));}
function fromUI(){let c={};for(const k of ids)c[k]=['interval','settle'].includes(k)?Number($(k).value):$(k).value.trim();return c;}
async function save(){return request('CONFIG',fromUI());}
async function act(fn){try{await fn();await refresh();}catch(e){status('Error: '+e.message+' Please contact Smarth for support.');}}
$('saveConfig').onclick=()=>act(async()=>{await save();status('Saved');});
$('useTab').onclick=()=>act(async()=>{const r=await request('USE_TAB');$('dashboard').value=r.url;await save();});
$('openTab').onclick=()=>act(async()=>{await save();await request('OPEN_TAB');});
$('signIn').onclick=()=>act(async()=>{await save();status('Opening Microsoft sign-in...');const r=await request('LOGIN');status(r.message);});
$('start').onclick=()=>act(async()=>{await save();await request('START');});
$('pause').onclick=()=>act(async()=>{await request('PAUSE');});
$('resume').onclick=()=>act(async()=>{await save();await request('RESUME');});
$('stop').onclick=()=>act(async()=>{await request('STOP');});
$('capture').onclick=()=>act(async()=>{await save();status('Capturing the Grafana background tab...');const r=await request('CAPTURE');lastPreview=r.preview;$('preview').src=r.preview;$('previewwrap').hidden=false;$('previewmeta').textContent='Visible viewport of selected Grafana tab';});
$('test').onclick=()=>act(async()=>{if(!confirm('Send one Outlook test email to the configured To/CC/BCC recipients?'))return;await save();status('Capturing and sending one test email...');const r=await request('TEST');status(r.message);});
$('export').onclick=()=>act(async()=>{const r=await request('LOGS');const blob=new Blob([JSON.stringify({app:'Smart Report v3',exportedAt:new Date().toISOString(),events:r.logs},null,2)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='smart-report-logs-'+new Date().toISOString().slice(0,10)+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),2000);});
refresh().catch(e=>status(e.message));

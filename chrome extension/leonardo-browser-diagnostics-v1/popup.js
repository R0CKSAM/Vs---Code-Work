const KEY = 'leonardoDiagnosticSessionV1';
const $ = x => document.getElementById(x);
let currentTab=null;
async function getTab(){ const tabs=await chrome.tabs.query({active:true,currentWindow:true});return tabs[0]; }
function eligible(tab){try{return new URL(tab?.url).hostname==='app.leonardo.ai';}catch{return false;}}
function notice(text,error=false){$('notice').textContent=text;$('notice').classList.toggle('error',error);}
async function render(){
  currentTab=await getTab();
  const data=(await chrome.storage.local.get(KEY))[KEY] || {recording:false,events:[]};
  $('eventCount').innerHTML=String(data.events?.length||0)+' <span>events</span>';
  $('dot').textContent=data.recording?'Recording':'Idle';
  $('dot').classList.toggle('active',!!data.recording);
  $('details').textContent=data.recording?'Observe one manual Leonardo generation cycle.':'Ready to capture UI transitions.';
  const ok=eligible(currentTab);
  $('start').disabled=!ok||!!data.recording;
  $('stop').disabled=!ok||!data.recording;
  $('mark').disabled=!ok||!data.recording;
  $('export').disabled=!(data.events?.length);
  if(!ok)notice('Open https://app.leonardo.ai/ and refresh the page before recording.',true);
  else notice('Read-only recording. No prompts, images, URLs, or account information are collected.');
}
async function action(kind){
  try {
    const tab=await getTab();
    if(!eligible(tab))throw Error('Open Leonardo AI first.');
    const result=await chrome.tabs.sendMessage(tab.id,{target:'leonardoDiagnostics',action:kind});
    if(!result?.ok)throw Error(result?.error||'Recorder not reachable. Refresh Leonardo.');
    await render();
  } catch(e){notice(e.message,true);}
}
$('start').onclick=()=>action('START');
$('stop').onclick=()=>action('STOP');
$('mark').onclick=()=>action('MARK');
$('clear').onclick=async()=>{if(!confirm('Delete the current diagnostic log?'))return;const t=await getTab(); if(eligible(t)){try{await chrome.tabs.sendMessage(t.id,{target:'leonardoDiagnostics',action:'CLEAR'});}catch{}} await chrome.storage.local.remove(KEY);render();};
$('export').onclick=async()=>{
  const data=(await chrome.storage.local.get(KEY))[KEY];
  if(!data?.events?.length)return;
  const exportData={format:'Leonardo Browser Diagnostics v1',createdAt:new Date().toISOString(),note:'Contains UI metadata only; review before sharing.',...data};
  const url=URL.createObjectURL(new Blob([JSON.stringify(exportData,null,2)],{type:'application/json'}));
  const a=document.createElement('a');a.href=url;a.download='leonardo-diagnostics-'+new Date().toISOString().replace(/[:.]/g,'-')+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),2000);
};
chrome.storage.onChanged.addListener((changes,area)=>{if(area==='local'&&changes[KEY])render();});
render();

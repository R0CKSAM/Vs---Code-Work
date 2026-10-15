const $ = id => document.getElementById(id);
const parse = str => str.split(/\r?\n/).map(x=>x.trim()).filter(Boolean);
async function tab(){const [t]=await chrome.tabs.query({active:true,currentWindow:true});if(!t?.url || !/^https:\/\/(chatgpt\.com|chat\.openai\.com)\//.test(t.url))throw Error('Open ChatGPT in the selected tab.');return t}
async function send(action){const t=await tab();await chrome.tabs.sendMessage(t.id,{action});}
async function save(){const prompts=parse($('prompts').value);if(!prompts.length)throw Error('Add at least one prompt.');await chrome.storage.local.set({master:$('master').value.trim(),prompts,index:0,phase:'idle',error:'',pending:null,tabId:null});}
async function operation(fn){try{await fn()}catch(e){$('detail').textContent=e.message}await refresh()}
$('save').onclick=()=>operation(save);
$('start').onclick=()=>operation(async()=>{await save();await send('START')});
$('pause').onclick=()=>operation(()=>send('PAUSE'));
$('resume').onclick=()=>operation(()=>send('RESUME'));
$('reset').onclick=()=>operation(()=>send('RESET'));
$('file').onchange=async e=>{const f=e.target.files?.[0];if(f)$('prompts').value=await f.text()};
async function refresh(){const d=await chrome.storage.local.get(['master','prompts','index','phase','error','pending']);$('status').textContent=d.phase||'idle';$('progress').textContent=`${d.index||0} / ${(d.prompts||[]).length}`;$('detail').textContent=d.error || (d.pending?`Waiting on Frame ${String((d.index||0)+1).padStart(2,'0')}…`: '')}
(async()=>{const d=await chrome.storage.local.get(['master','prompts']);$('master').value=d.master||'';$('prompts').value=(d.prompts||[]).join('\n');await refresh();setInterval(refresh,1200)})();

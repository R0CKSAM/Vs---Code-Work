const $=id=>document.getElementById(id),parse=s=>s.split(/\r?\n/).map(x=>x.trim()).filter(Boolean),uid=()=>`${Date.now()}-${Math.random().toString(36).slice(2)}`;
const safe=s=>String(s||'').slice(0,700);
let importBusy=false;
function importNotice(title,message,error=false){
 const box=$('importNotice'),heading=document.createElement('strong'),body=document.createElement('p');
 heading.textContent=title;body.textContent=message;box.replaceChildren(heading,body);box.hidden=false;box.classList.toggle('import-error',error);box.setAttribute('role',error?'alert':'status');
 if(error){box.scrollIntoView({block:'nearest'});box.focus({preventScroll:true});}
}
async function tab(){const [t]=await chrome.tabs.query({active:true,currentWindow:true});if(!t?.url||!/^https:\/\/(chatgpt\.com|chat\.openai\.com)\//.test(t.url))throw Error('Open your ChatGPT tab to start.');return t;}
async function send(action){const t=await tab();const r=await chrome.tabs.sendMessage(t.id,{action,tabId:t.id});if(!r?.ok)throw Error(r?.error||'Could not contact ChatGPT tab. Refresh the page and try again.');}
function renderHistory(items,queueId){const box=$('historyList');const rows=items.filter(x=>x.queueId===queueId).slice(-8).reverse();box.replaceChildren();if(!rows.length){box.textContent='No frame results yet.';return;}for(const x of rows){const item=document.createElement('div');item.className='history-item';const a=document.createElement('strong');a.textContent=x.label||`Row ${x.index+1}`;const b=document.createElement('span');b.className=x.status==='completed'?'good':'bad';b.textContent=x.status;item.append(a,b);box.append(item);}}
function showError(e){$('alert').hidden=false;$('alert').textContent=`${safe(e?.message||e)} — Please contact Smarth for support. You can download error logs below.`;}
async function refresh(){const d=await chrome.storage.local.get(['prompts','index','phase','error','pending','activity','frameHistory','queueId','autoDownload','completionNotifications']);const list=d.prompts||[],i=Math.max(0,Math.min(d.index||0,list.length)),ph=d.phase||'idle',pct=list.length?Math.round(i/list.length*100):0;
 $('progressBig').innerHTML=`${i} <small>/ ${list.length}</small>`;$('pct').textContent=`${pct}%`;$('barFill').style.width=pct+'%';$('phasePill').textContent=ph==='done'?'COMPLETE':ph.toUpperCase();$('phasePill').className='phase-pill '+ph;
 const line=list[i]||'',label=line.includes('||')?line.split('||')[0].trim():`Row ${i+1}`;
 $('frameNow').textContent=!list.length?'Upload a storyboard to begin':i>=list.length?'All frames completed':`${label} · ${i+1} of ${list.length}`;
 $('activity').textContent=safe(d.error||d.activity||'Ready when you are.');$('loaded').textContent=list.length?`${list.length} FRAMES LOADED`:'NO FILE';
 $('start').disabled=!list.length||ph==='running'||ph==='done';$('pause').disabled=ph!=='running';$('resume').disabled=!list.length||ph==='running'||ph==='done';$('stop').disabled=!list.length||['idle','stopped','done'].includes(ph);
 renderHistory(d.frameHistory||[],d.queueId);$('complete').disabled=!d.pending;$('retry').disabled=!d.pending;$('setRow').disabled=!!d.pending||ph==='running';
 if(d.error){$('alert').hidden=false;$('alert').textContent=`${safe(d.error)} Please contact Smarth for support. Download error logs below.`;}else{$('alert').hidden=true;}
}
async function op(fn){try{await fn();await refresh()}catch(e){showError(e)}}
async function replaceQueue(master,prompts,filename){if(!prompts.length)throw Error('Your file contains no frame prompts.');const old=await chrome.storage.local.get(['phase','pending']);if((old.phase==='running'||old.pending)&&!confirm('Replace the existing queue? Do this only when the current image is complete.'))return false;try{await send('PAUSE')}catch{}await chrome.storage.local.set({master,prompts,index:0,phase:'idle',pending:null,queueId:uid(),ownerTabId:null,manualDone:true,frameHistory:[],error:'',activity:`Loaded ${prompts.length} frames from ${filename}.`});return true;}
$('autoDownload').onchange=async e=>chrome.storage.local.set({autoDownload:e.target.checked});
$('notifyDone').onchange=async e=>chrome.storage.local.set({completionNotifications:e.target.checked});
$('exportHistory').onclick=async()=>{const d=await chrome.storage.local.get(['frameHistory','queueId']);const h=(d.frameHistory||[]).filter(x=>x.queueId===d.queueId);const esc=v=>'"'+String(v??'').replaceAll('"','""')+'"';const csv=[['Excel row','Frame','Status','Timestamp','Notes'],...h.map(x=>[x.index+1,x.label,x.status,x.at,x.note])].map(row=>row.map(esc).join(',')).join('\r\n');const blob=new Blob([csv],{type:'text/csv;charset=utf-8'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='storyboard-frame-history.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),2500)};
$('file').onclick=e=>e.stopPropagation();$('dropzone').onclick=()=>$('file').click();$('dropzone').onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();$('file').click()}};
for(const event of ['dragenter','dragover'])$('dropzone').addEventListener(event,e=>{e.preventDefault();$('dropzone').classList.add('drag')});for(const event of ['dragleave','drop'])$('dropzone').addEventListener(event,e=>{e.preventDefault();$('dropzone').classList.remove('drag')});$('dropzone').ondrop=e=>{const f=e.dataTransfer?.files?.[0];if(f)importFile(f)};
async function importFile(f){
 if(importBusy)return;importBusy=true;let changed=false;
 $('file').disabled=true;$('dropzone').setAttribute('aria-busy','true');
 importNotice('Checking your file…','Checking the storyboard format before replacing your queue.');
 try{
  const result=await StoryboardImport.read(f),d=await chrome.storage.local.get(['master']);
  const master=result.master!==null?result.master:(d.master||'');
  if(!await replaceQueue(master,result.prompts,f.name)){importNotice('Upload cancelled','Your current queue was kept.');return;}
  changed=true;$('master').value=master;$('prompts').value=result.prompts.join('\n');
  $('fileTitle').textContent=f.name;$('fileSub').textContent=`${result.count} frames ready · Loaded successfully`;
  await refresh();
  importNotice(`Loaded ${result.count} frames`,(result.warnings||[]).join(' ')||'Your storyboard is ready. Choose a starting frame, then Start.');
 }catch(e){
  importNotice(changed?'Storyboard loaded; display could not refresh':'File not imported',safe(e?.message||e)+' '+(changed?'Reopen the popup to see the loaded queue.':'Your current queue was kept. For Excel / CSV, use Frame | Master Prompt | Scene Prompt headers on the first worksheet, one frame per row and one shared master prompt. Scene Prompt is required. Use Download example Excel below the upload box.'),true);
 }finally{importBusy=false;$('file').disabled=false;$('file').value='';$('dropzone').removeAttribute('aria-busy');}
}
$('file').onchange=e=>{const f=e.target.files?.[0];if(f)importFile(f)};
$('example').onclick=()=>{const a=document.createElement('a');a.href=chrome.runtime.getURL('storyboard-example.xlsx');a.download='storyboard-example.xlsx';a.click()};
$('start').onclick=()=>op(()=>send('START'));$('pause').onclick=()=>op(()=>send('PAUSE'));$('resume').onclick=()=>op(()=>send('RESUME'));
$('stop').onclick=()=>op(async()=>{if(!confirm('Stop the queue after the current action? Progress will be preserved; you can Resume later.'))return;await send('PAUSE');await chrome.storage.local.set({phase:'stopped',activity:'Stopped safely. Your current frame is preserved; Resume when ready.'})});
$('save').onclick=()=>op(async()=>{const prompts=parse($('prompts').value),master=$('master').value.trim(),d=await chrome.storage.local.get(['prompts','master']);if(JSON.stringify(prompts)===JSON.stringify(d.prompts||[])&&master===(d.master||''))return;await replaceQueue(master,prompts,'edited fields')});
$('setRow').onclick=()=>op(async()=>{const d=await chrome.storage.local.get(['prompts','phase','pending']);if(d.phase==='running'||d.pending)throw Error('Pause and resolve the current frame before selecting a different row.');const row=Number($('startRow').value),n=(d.prompts||[]).length;if(!Number.isInteger(row)||row<1||row>n)throw Error(`Choose a row from 1 to ${n}.`);if(!confirm(`Jump to imported row ${row}? Only do this if the earlier frames are complete.`))return;await chrome.storage.local.set({index:row-1,phase:'paused',pending:null,error:'',activity:`Ready to continue from row ${row}.`})});
$('complete').onclick=()=>op(async()=>{if(confirm('Do you SEE the completed image for this frame?'))await send('COMPLETE')});$('retry').onclick=()=>op(async()=>{if(confirm('Retry only if this frame definitely did not generate. A duplicate is possible.'))await send('RETRY')});$('reset').onclick=()=>op(async()=>{if(confirm('Reset progress to the first frame?'))await send('RESET')});
$('logs').onclick=async()=>{try{const d=await chrome.storage.local.get(['diagnosticEvents','error','activity','index','phase','pending','prompts','frameHistory']);const payload={app:'Smart Flow',version:'19.0.0',exportedAt:new Date().toISOString(),support:'Please contact Smarth for support.',status:{phase:d.phase,index:d.index,total:(d.prompts||[]).length,pendingState:d.pending?.state||null,lastError:d.error||null,lastActivity:d.activity||null},events:d.diagnosticEvents||[],history:(d.frameHistory||[]).map(x=>({index:x.index,label:x.label,status:x.status,at:x.at,note:x.note}))};const blob=new Blob([JSON.stringify(payload,null,2)],{type:'application/json'});const u=URL.createObjectURL(blob),a=document.createElement('a');a.href=u;a.download=`storyboard-error-log-${new Date().toISOString().slice(0,10)}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(u),2000)}catch(e){showError(e)}};
(async()=>{const d=await chrome.storage.local.get(['master','prompts','autoDownload','completionNotifications']);$('autoDownload').checked=!!d.autoDownload;$('notifyDone').checked=d.completionNotifications!==false;if(d.completionNotifications===undefined)await chrome.storage.local.set({completionNotifications:true});$('master').value=d.master||'';$('prompts').value=(d.prompts||[]).join('\n');if((d.prompts||[]).length){$('fileTitle').textContent='Storyboard ready';$('fileSub').textContent=`${d.prompts.length} frames saved locally`;}await refresh();setInterval(refresh,1700)})();
// Optional user-selected logo. Browser toolbar icon can be customized at runtime.
async function applySmartLogo(src,save=false){
 const bitmap=await createImageBitmap(await (await fetch(src)).blob());
 const iconSet={};
 for(const size of [16,32,48,128]){
  const c=document.createElement('canvas');c.width=c.height=size;
  const x=c.getContext('2d');x.clearRect(0,0,size,size);
  const edge=Math.min(bitmap.width,bitmap.height),sx=(bitmap.width-edge)/2,sy=(bitmap.height-edge)/2;
  x.drawImage(bitmap,sx,sy,edge,edge,0,0,size,size);
  iconSet[size]=x.getImageData(0,0,size,size);
 }
 await chrome.action.setIcon({imageData:iconSet});
 $('brandLogo').src=src;
 if(save)await chrome.storage.local.set({smartFlowLogo:src});
 bitmap.close();
}
$('customLogoFile').addEventListener('change',async e=>{
 try{
  const f=e.target.files?.[0];if(!f)return;
  if(!['image/png','image/jpeg','image/webp'].includes(f.type))throw Error('Choose a PNG, JPG or WebP image.');
  if(f.size>1500000)throw Error('Logo must be under 1.5 MB.');
  const src=await new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result);r.onerror=reject;r.readAsDataURL(f)});
  await applySmartLogo(src,true);
 }catch(err){showError(err)}
});
$('resetLogo').onclick=async()=>{
 try{
  const icons={16:'icon16.png',32:'icon32.png',48:'icon48.png',128:'icon128.png'};
  await chrome.action.setIcon({path:icons});
  await chrome.storage.local.remove('smartFlowLogo');$('brandLogo').src='icon48.png';$('customLogoFile').value='';
 }catch(err){showError(err)}
};
chrome.storage.local.get('smartFlowLogo').then(d=>{if(d.smartFlowLogo)applySmartLogo(d.smartFlowLogo).catch(showError)});

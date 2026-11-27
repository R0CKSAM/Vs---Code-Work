import {SIZES,sizeFolder,stem,isSource,promptFor,correctionPrompt,MAX_CORRECTIONS} from './core.mjs';
const $=id=>document.getElementById(id);
let root=null,active=false,busy=false,looping=false,state={jobs:[],pending:null,tabId:null,status:'idle',message:'Choose an image folder to begin.'};
const db=await new Promise((resolve,reject)=>{const r=indexedDB.open('smart-banner-gen',1);r.onupgradeneeded=()=>r.result.createObjectStore('data');r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});
function store(key,value){return new Promise((resolve,reject)=>{const tx=db.transaction('data','readwrite');tx.objectStore('data').put(value,key);tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error);});}
function read(key){return new Promise((resolve,reject)=>{const r=db.transaction('data').objectStore('data').get(key);r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});}
async function persist(){await store('state',state);render();}
function render(){
  const done=state.jobs.filter(j=>['saved','existing'].includes(j.status)).length;
  $('progress').max=state.jobs.length||1;$('progress').value=done;
  $('status').textContent=`${state.status.toUpperCase()} · ${done} / ${state.jobs.length} formats ready`;
  $('detail').textContent=state.message||'';
  $('folderName').textContent=root?.name||'No folder selected';
  for(const id of ['folder','scan','landscape','portrait','direction','tab','limit']) $(id).disabled=active||busy||looping;
  $('start').disabled=active||busy||looping||!state.jobs.length;
  $('retry').disabled=active||looping||!state.pending;
  $('pause').disabled=!active;
  $('expand').disabled=busy||!root;
  $('queue').replaceChildren(...state.jobs.slice(0,250).map(j=>{const div=document.createElement('div');div.className='job';const b=document.createElement('b');b.textContent=j.status;div.append(b,document.createTextNode(`${j.category||root?.name||''} / ${j.name} → ${sizeFolder(j)}${j.note?' · '+j.note:''}`));return div;}));
  if(state.jobs.length>250){const p=document.createElement('p');p.textContent=`Showing first 250 of ${state.jobs.length} formats. Save history for the complete list.`;$('queue').append(p);}
}
function showError(e){$('error').hidden=false;$('error').textContent=e.message||String(e);}
function clearError(){$('error').hidden=true;}
async function folderAccess(){if(!root) throw Error('Choose your image folder first.');if(await root.queryPermission({mode:'readwrite'})!=='granted'&&await root.requestPermission({mode:'readwrite'})!=='granted')throw Error('Folder write permission is needed to save outputs.');}
async function categoryHandle(j){return j.category?root.getDirectoryHandle(j.category):root;}
async function sourceFile(j){return (await (await categoryHandle(j)).getFileHandle(j.name)).getFile();}
async function maybeFile(dir,name){try{return await(await dir.getFileHandle(name)).getFile();}catch(e){if(e.name==='NotFoundError')return null;throw e;}}
async function dimensions(blob){const bitmap=await createImageBitmap(blob);const dims={w:bitmap.width,h:bitmap.height};bitmap.close();return dims;}
async function outputExists(j){
  const cat=await categoryHandle(j);let dir;
  try{dir=await cat.getDirectoryHandle(sizeFolder(j));}catch(e){if(e.name==='NotFoundError')return false;throw e;}
  for await(const [name,handle] of dir.entries()){
    if(handle.kind!=='file'||!isSource(name)||stem(name)!==j.key)continue;
    try{const d=await dimensions(await handle.getFile());if(d.w===j.w&&d.h===j.h)return true;}catch{}
  }return false;
}
async function write(dir,name,blob){const handle=await dir.getFileHandle(name,{create:true});const stream=await handle.createWritable();try{await stream.write(blob);await stream.close();}catch(e){await stream.abort().catch(()=>{});throw e;}}
async function archive(cat,name,blob){
  const bin=await cat.getDirectoryHandle('bin',{create:true});const suffix=`${Date.now()}_${crypto.randomUUID().slice(0,8)}`;
  const dot=name.lastIndexOf('.');
  await write(bin,dot>=0?`${name.slice(0,dot)}_${suffix}${name.slice(dot)}`:`${name}_${suffix}`,blob);
}
async function saveOutput(j,blob){
  if(await outputExists(j))return {status:'existing',note:'Valid output already exists; kept unchanged'};
  const bitmap=await createImageBitmap(blob);let png;
  const mismatch=bitmap.width!==j.w||bitmap.height!==j.h;
  try{
    if(mismatch)throw Error(`Refusing wrong-size output: ${bitmap.width} × ${bitmap.height}; expected ${j.w} × ${j.h}.`);
    const cat=await categoryHandle(j);
    const canvas=document.createElement('canvas');canvas.width=j.w;canvas.height=j.h;
    const ctx=canvas.getContext('2d');ctx.drawImage(bitmap,0,0);
    png=await new Promise((resolve,reject)=>canvas.toBlob(b=>b?resolve(b):reject(Error('PNG encoding failed.')),'image/png'));
    const dir=await cat.getDirectoryHandle(sizeFolder(j),{create:true}),name=j.key+'.png',existing=await maybeFile(dir,name);
    if(existing){await archive(cat,`${j.key}_${j.w}x${j.h}_previous.png`,existing);}
    await write(dir,name,png);
    const verified=await dimensions(await(await dir.getFileHandle(name)).getFile());
    if(verified.w!==j.w||verified.h!==j.h)throw Error('Saved dimensions did not pass verification.');
    return {status:'saved',note:'ChatGPT/source exact dimensions verified; no local resizing'};
  } finally {bitmap.close();}
}
async function tabs(){const selected=state.tabId||Number($('tab').value);const options=(await chrome.tabs.query({})).filter(t=>/^https:\/\/(chatgpt\.com|chat\.openai\.com)\//.test(t.url||''));$('tab').replaceChildren(new Option('Choose a dedicated ChatGPT conversation',''),...options.map(t=>new Option(t.title||t.url,t.id)));if(options.some(t=>t.id===selected))$('tab').value=selected;}
async function rpc(type,payload={}){let r;try{r=await chrome.tabs.sendMessage(state.tabId,{type,...payload});}catch{throw Error('Cannot reach the selected ChatGPT tab. Reload it after installing the extension, then choose it again.');}if(!r?.ok)throw Error(r?.error||'ChatGPT did not respond.');return r;}
async function dataUrl(blob){return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(reader.error);reader.readAsDataURL(blob);});}
async function fetchCandidate(url){
  try{const r=await rpc('BANNER_ASSET',{url});return await(await fetch(r.dataUrl)).blob();}
  catch(error){
    const parsed=new URL(url);
    if(parsed.protocol!=='https:'||!/^(?:chatgpt\.com|chat\.openai\.com|(?:[a-z0-9-]+\.)*(?:oaiusercontent|oaistatic)\.com)$/.test(parsed.hostname))throw error;
    const r=await fetch(url,{signal:AbortSignal.timeout(45000)});if(!r.ok)throw error;
    const blob=await r.blob();if(blob.size>30*1024*1024)throw Error('Output exceeds 30 MB.');return blob;
  }
}
async function step(){
  const j=state.jobs.find(x=>!['saved','existing'].includes(x.status));
  if(!j){state.status='complete';state.message='All formats are saved. Review text, faces and branding before publishing.';active=false;return;}
  if(await outputExists(j)){j.status='existing';state.pending=null;return;}
  if(!state.pending){
    const source=await sourceFile(j),d=await dimensions(source);
    if(!active)return;
    if(d.w===j.w&&d.h===j.h){Object.assign(j,await saveOutput(j,source));j.note='Source already matches exact dimensions; copied as PNG';return;}
    const token=crypto.randomUUID();j.token=token;j.status='waiting';
    state.pending={token,jobId:j.id,started:Date.now(),lastSignature:'',stableSince:0};
    state.message=`Uploading ${j.name} for ${sizeFolder(j)}. Waiting for a verified attachment.`;
    await persist(); // Save before any upload or send: uncertain submissions are never repeated.
    if(source.size>20*1024*1024)throw Error('Source image exceeds 20 MB. Reduce it before uploading.');
    const upload=await dataUrl(source);
    if(!active)return;
    const result=await rpc('BANNER_RUN',{token,name:j.name,dataUrl:upload,prompt:promptFor(j,state.direction)});
    state.pending.path=result.path;state.message=`Waiting for ${j.name} · ${sizeFolder(j)}. You may use other tabs.`;return;
  }
  const p=state.pending;
  if(p.jobId!==j.id)throw Error('Queue checkpoint does not match the current job. Save history and rescan.');
  if(p.followup&&p.needsSend){
    if(!active)return;
    p.needsSend=false;await persist();
    if(!active){p.needsSend=true;return;}
    await rpc('BANNER_RUN',{token:p.token,followup:true,parentToken:p.parentToken,path:p.path,prompt:p.prompt});
    state.message=`Asked ChatGPT for an exact-size downloadable file (${p.corrections}/${MAX_CORRECTIONS}). Waiting for ${sizeFolder(j)}.`;
    return;
  }
  const r=await rpc('BANNER_POLL',p);
  if(!r.found){
    if(!p.followup&&!p.resumedDraft){
      const check=await rpc('BANNER_CHECK');
      if(check.draftToken===p.token&&!check.working&&active){p.resumedDraft=true;await persist();if(!active){p.resumedDraft=false;return;}await rpc('BANNER_RUN',{token:p.token,name:j.name,resumePrepared:true,dataUrl:await dataUrl(await sourceFile(j)),prompt:promptFor({...j,token:p.token},state.direction)});return;}
    }
    if(Date.now()-p.started>150000)throw Error('Submission could not be verified. Inspect ChatGPT. If nothing was sent, clear its draft and choose Retry an unsent job.');return;
  }
  p.path=r.path;
  if(Date.now()-p.started>25*60*1000)throw Error('This job has waited 25 minutes. Check ChatGPT for limits or an incomplete generation; Resume will check the same job.');
  if(!r.idle){p.stableSince=0;return;}
  const signature=JSON.stringify(r.urls);
  if(p.lastSignature!==signature){p.lastSignature=signature;p.stableSince=Date.now();return;}
  if(!p.stableSince)p.stableSince=Date.now();
  if(Date.now()-p.stableSince<12000)return;
  if(!r.urls.length){
    if(/(?:limit|try again later|unable to|cannot|can't|could not|please (?:clarify|confirm|provide)|what (?:text|size|style)|which (?:text|size|style))/i.test(r.text))throw Error('ChatGPT needs attention. '+r.text.slice(-700));
    await requestCorrection(j,p,r,'');return;
  }
  let chosen=null,largest=null,lastError='';
  for(const url of r.urls){
    try{const blob=await fetchCandidate(url),d=await dimensions(blob);if(d.w===j.w&&d.h===j.h){chosen=blob;break;}if(!largest||d.w*d.h>largest.area)largest={blob,area:d.w*d.h};}catch(e){lastError=e.message;}
  }
  if(!chosen){
    if(!largest){await requestCorrection(j,p,r,'');return;}
    const d=await dimensions(largest.blob);
    const cat=await categoryHandle(j),ext=({'image/png':'png','image/jpeg':'jpg','image/webp':'webp','image/avif':'avif'})[largest.blob.type]||'img';
    if(!p.archived){await archive(cat,`${j.key}_${j.w}x${j.h}_rejected.${ext}`,largest.blob);p.archived=true;await persist();}
    await requestCorrection(j,p,r,`${d.w} × ${d.h}`);return;
  }
  Object.assign(j,await saveOutput(j,chosen));state.pending=null;state.message=`Saved ${j.key}.png · ${sizeFolder(j)} · ${j.note}`;
}
async function requestCorrection(j,p,r,observed){
  if((p.corrections||0)>=MAX_CORRECTIONS)throw Error(`ChatGPT has not supplied a verified ${j.w} × ${j.h} file after ${MAX_CORRECTIONS} follow-ups. Wrong-size outputs remain in bin; no final image was accepted. Inspect the conversation and Resume after correcting its downloadable file.`);
  if(!active)return;
  const token=crypto.randomUUID();
  state.pending={token,parentToken:p.token,jobId:j.id,path:r.path,followup:true,needsSend:true,corrections:(p.corrections||0)+1,started:Date.now(),lastSignature:'',stableSince:0,prompt:correctionPrompt(j,token,observed)};
  state.message=`${observed?'Wrong dimensions: '+observed:'No downloadable image found'}. Preparing an exact-file follow-up to ChatGPT.`;
  await persist();
}
async function run(){
  looping=true;render();
  try {
  await navigator.locks.request('smart-banner-generation',{ifAvailable:true},async lock=>{
    if(!lock)throw Error('Smart Banner Gen is already running in another workspace.');
    await chrome.runtime.sendMessage({type:'POWER',on:true});
    try{while(active){await step();await persist();if(active)await new Promise(r=>setTimeout(r,5000));}}
    catch(e){active=false;state.status='paused';state.message='Paused safely. The current job is retained.';showError(e);await persist();}
    finally{active=false;await chrome.runtime.sendMessage({type:'POWER',on:false});render();}
  });
  } finally {looping=false;render();}
}
function action(id,fn){$(id).addEventListener('click',async()=>{clearError();try{await fn();}catch(e){showError(e);}});}
action('folder',async()=>{const picked=await showDirectoryPicker({mode:'readwrite',id:'smart-banner-images'});if(state.jobs.length&&!confirm('Selecting a folder resets this workspace queue. Existing images remain untouched. Continue?'))return;root=picked;state={jobs:[],pending:null,status:'idle',message:'Folder selected. Scan to build the queue.'};await store('root',root);await persist();});
action('refresh',tabs);
action('expand',async()=>{
  await folderAccess();if(busy)return;busy=true;render();
  try{
    const sources=[];
    async function collect(dir,category){const keys=new Set();for await(const [name,h]of dir.entries()){
      if(h.kind!=='file'||!isSource(name))continue;
      const key=stem(name);if(keys.has(key.toLowerCase()))throw Error(`Duplicate source key ${key}; resolve it before expanding.`);keys.add(key.toLowerCase());sources.push({name,key,category});
    }}
    await collect(root,'');
    for await(const [name,h]of root.entries())if(h.kind==='directory'&&!/^(?:bin|1920\s*[×x]\s*1080 px|400\s*[×x]\s*711 px)$/i.test(name))await collect(h,name);
    sources.sort((a,b)=>(a.category+'/'+a.name).localeCompare(b.category+'/'+b.name));
    const selected=SIZES.filter(s=>s.w===1920?$('landscape').checked:$('portrait').checked);
    if(!selected.length)throw Error('Choose at least one format.');
    const identity=j=>JSON.stringify([j.category.toLowerCase(),j.key.toLowerCase(),j.w,j.h]);
    const known=new Set(state.jobs.map(identity));const additions=[];
    for(const src of sources)for(const size of selected){const j={...src,...size,id:crypto.randomUUID(),status:'queued'};if(known.has(identity(j)))continue;known.add(identity(j));if(await outputExists(j))j.status='existing';additions.push(j);}
    // Append in place: retain the current pending job and any saves completed
    // while directory enumeration was running. Never replace the live state.
    state.jobs.push(...additions);
    if(state.status==='complete'&&additions.some(j=>j.status==='queued'))state.status='ready';
    state.message=`Whole folder: ${sources.length} sources; ${state.jobs.length} formats. Added ${additions.length}; current checkpoint preserved.`;
    $('limit').value='0';$('scanInfo').textContent=state.message;await persist();
  }finally{busy=false;render();}
});
action('scan',async()=>{
  await folderAccess();if(state.pending&&!confirm('A job is pending. Rescanning forgets its checkpoint and could cause a duplicate generation. Continue only after reviewing ChatGPT.'))return;
  const sizes=SIZES.filter(s=>s.w===1920?$('landscape').checked:$('portrait').checked);if(!sizes.length)throw Error('Choose at least one output format.');
  busy=true;render();try{
    const sources=[];
    async function collect(dir,category){const keys=new Set();for await(const [name,h]of dir.entries()){if(h.kind!=='file'||!isSource(name))continue;const key=stem(name);if(keys.has(key.toLowerCase()))throw Error(`Two sources share video key ${key} in ${category||root.name}. Resolve the duplicate before scanning.`);keys.add(key.toLowerCase());sources.push({name,key,category});}}
    await collect(root,'');for await(const [name,h]of root.entries())if(h.kind==='directory'&&!/^(?:bin|1920\s*[×x]\s*1080 px|400\s*[×x]\s*711 px)$/i.test(name))await collect(h,name);
    sources.sort((a,b)=>(a.category+'/'+a.name).localeCompare(b.category+'/'+b.name));
    const limit=Number($('limit').value);
    if(!Number.isInteger(limit)||limit<0)throw Error('Image limit must be a whole number, 0 or greater.');
    if(limit)sources.splice(limit);
    const jobs=[];for(const src of sources)for(const size of sizes){const j={...src,...size,id:crypto.randomUUID(),status:'queued'};if(await outputExists(j))j.status='existing';jobs.push(j);}
    state={jobs,pending:null,tabId:Number($('tab').value)||null,status:'ready',message:`${sources.length} source images; ${jobs.length} formats; ${jobs.filter(j=>j.status==='existing').length} existing valid outputs.`,direction:$('direction').value};
    $('scanInfo').textContent=state.message;await persist();
  }finally{busy=false;render();}
});
action('start',async()=>{
  await folderAccess();state.tabId=Number($('tab').value);if(!state.tabId)throw Error('Choose the dedicated ChatGPT tab.');
  const check=await rpc('BANNER_CHECK');if(!check.ready)throw Error('Open and sign into ChatGPT first.');
  if(!state.pending&&(!check.clean||!check.idle))throw Error('Use an idle conversation with no unsent draft or attachment.');
  if(check.version!=='1.1.2')throw Error('Reload this ChatGPT tab to activate Smart Banner Gen 1.1.2 before starting.');
  state.direction=$('direction').value;state.status='running';
  if(state.pending){state.pending.started=Date.now();if(check.draftToken===state.pending.token)state.pending.resumedDraft=false;}active=true;await persist();run().catch(async e=>{active=false;state.status='paused';showError(e);await persist();});
});
action('pause',async()=>{active=false;state.status='paused';state.message='Pause requested. An in-progress file save may finish; generated responses stay available for Resume.';await rpc('BANNER_CANCEL').catch(()=>{});await persist();});
action('retry',async()=>{await folderAccess();const r=await rpc('BANNER_POLL',state.pending);if(r.found)throw Error('This job was submitted. Use Resume to retrieve it; it will not be sent again.');const check=await rpc('BANNER_CHECK');if(!check.clean||!check.idle||check.working)throw Error('First review and clear the unsent draft/attachment in ChatGPT.');if(state.pending.followup)state.pending.needsSend=true;else{const job=state.jobs.find(j=>j.id===state.pending.jobId);job.status='queued';state.pending=null;}state.message='Unsent checkpoint reset. Start when ready.';await persist();});
action('report',async()=>{await folderAccess();await write(root,`Smart_Banner_history_${Date.now()}.json`,new Blob([JSON.stringify({at:new Date().toISOString(),...state},null,2)],{type:'application/json'}));state.message='History saved in the selected folder.';render();});
root=await read('root')||null;state=await read('state')||state;
if(state.status==='running'){state.status='paused';state.message='Workspace reopened. Restore folder permission and Resume to check the saved checkpoint.';}
$('direction').value=state.direction||'';
if(root)$('permission').textContent='Folder remembered. Chrome may ask for access again when you resume.';
await tabs();render();

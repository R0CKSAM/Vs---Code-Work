// Reference images stay local until the employee explicitly attaches them.
(()=>{
 const el=id=>document.getElementById(id);
 const names=['Anaya Character Reference Sheet.png','Arjun Anime Character Reference Sheet.png','Mehak Character Reference Sheet.png','Trisha Anime Character Reference Sheet.png','Veer Anime Character Reference Sheet.png'];
 const required=s=>/REFERENCE SET REQUIRED:/.test(s.master||'');
 const read=file=>new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve({name:file.name,type:file.type,dataUrl:r.result});r.onerror=()=>reject(Error('Could not read '+file.name));r.readAsDataURL(file)});
 async function save(files,mappingKey){
  const s=await chrome.storage.local.get(['phase','pending']);
  if(s.phase==='running'||s.pending)throw Error('Finish or reset the pending frame before changing its references.');
  if(!files.length||files.length>8)throw Error('Choose between 1 and 8 character reference images.');
  if(files.some(f=>!['image/png','image/jpeg','image/webp'].includes(f.type)||f.size>10_000_000)||files.reduce((n,f)=>n+f.size,0)>40_000_000)throw Error('Use PNG, JPG or WebP references, under 10 MB each and 40 MB in total.');
  const images=await Promise.all(files.map(read));
  await chrome.storage.local.set({referenceImages:images,referenceSummary:{revision:uid(),names:images.map(f=>f.name),...(mappingKey?{mappingKey}:{})},referenceSession:null});
 }
 async function refresh(s){
  if(!el('referenceStatus'))return;
  const summary=s.referenceSummary,n=summary?.names?.length||0,session=s.referenceSession;
  el('referenceStatus').textContent=!n?(required(s)?'Required for this workbook: load all five Aarohan reference sheets before Start.':'Optional: choose character images to attach before your first frame.'):
    session?.revision===summary.revision?(session.state==='ready'?'References confirmed in ChatGPT. Start will include them with the first frame.':session.state==='sent'?'Reference images sent with the first frame. Keep using the same conversation.':'Upload requested. Check all attachments in ChatGPT, wait for upload to finish, then confirm below.'):
    `${n} references saved locally. Attach them to your ChatGPT conversation before Start.`;
  el('referenceNames').textContent=(summary?.names||[]).join(' · ');
  const locked=operationBusy||importBusy||s.phase==='running'||!!s.pending;
  el('autoReferences').checked=s.autoReferences!==false;
  el('allowReferenceGaps').checked=!!s.allowReferenceGaps;
  for(const id of ['autoReferences','allowReferenceGaps'])el(id).disabled=locked;
  for(const id of ['autoReferences','allowReferenceGaps'])el(id).closest('label').hidden=!(s.mappedPack||s.frameReferences);
  for(const id of ['aarohanReferences','chooseReferences','referenceFiles','clearReferences'])el(id).disabled=locked;
  el('attachReferences').disabled=locked||!n;
  el('confirmReferences').hidden=!n||session?.state!=='attached';
  el('confirmReferences').disabled=locked;
  el('clearReferences').hidden=!n;
  el('referencePanel').classList.toggle('reference-required',required(s)&&!n);
  el('chooseReferencePack').disabled=locked;
  for(const id of ['aarohanReferences','chooseReferences'])el(id).hidden=!!(s.mappedPack||s.frameReferences);
  if(s.mappedPack||s.frameReferences){
   el('referencePanel').querySelector('.caption-muted').textContent=s.autoReferences!==false?'AUTOMATIC':'MANUAL';
   const mapping=s.frameReferences?.[s.index||0],ready=mapping&&summary?.mappingKey===JSON.stringify(mapping);
   el('referenceStatus').textContent=!mapping?'Load the reference pack folder after importing a pack CSV.':!ready?'Current frame requires: '+(mapping.files.join(', ')||'no mapped images')+'. Choose Attach frame references.':el('referenceStatus').textContent;
   if(ready&&!mapping.files.length)el('referenceStatus').textContent='No images mapped for this frame. Reference gap reviewed. Choose Start or Resume.';
   if(mapping?.gap)el('referenceStatus').textContent+=' Reference gap: '+mapping.gap;
   el('attachReferences').disabled=locked||!mapping;
   if(!ready)el('nextStep').textContent=el('referenceStatus').textContent;
   if(s.autoReferences!==false&&mapping){
    el('referenceStatus').textContent=s.phase==='running'?(s.activity||'Uploading references and generating scenes automatically.'):'Automatic references ready. Choose Start or Resume; matching images will upload before the scene prompt.';
    if(mapping.gap&&!s.allowReferenceGaps)el('referenceStatus').textContent+=' This frame has a reference gap to review: '+mapping.gap;
    el('nextStep').textContent=el('referenceStatus').textContent;
   }
   if(s.phase==='paused'&&s.error){el('referenceStatus').textContent='Action needed: '+s.error;el('nextStep').textContent='Read the reference message, resolve it, then Resume. Your frame is preserved.';}
   if(s.phase==='done'){el('referenceStatus').textContent='All mapped scenes completed. Reference images remain saved locally.';el('nextStep').textContent='All frames finished. Import another scene CSV and load its reference pack to begin.';}
  }else{
   el('referencePanel').querySelector('.caption-muted').textContent='BEFORE START';
  }
  if(!(s.mappedPack&&s.autoReferences!==false)&&!['running','done'].includes(s.phase)&&(required(s)||n)&&!['ready','sent'].includes(session?.state))el('nextStep').textContent=!n?'Before Start: load the five Aarohan reference sheets below.':session?.state==='attached'?'Check all reference thumbnails in ChatGPT, wait for uploads to finish, then confirm them above.':'Before Start: attach your saved references to ChatGPT, then confirm the uploads.';
 }
 el('aarohanReferences').onclick=()=>op(async()=>{
  const files=await Promise.all(names.map(async name=>{const response=await fetch(chrome.runtime.getURL('character-references/'+name));if(!response.ok)throw Error('The packaged reference is missing: '+name);return new File([await response.blob()],name,{type:'image/png'});}));
  await save(files);
 });
 el('chooseReferences').onclick=()=>el('referenceFiles').click();
 for(const id of ['autoReferences','allowReferenceGaps'])el(id).onchange=e=>{const checked=e.target.checked;op(async()=>{
  const s=await chrome.storage.local.get(['phase','pending']);if(s.phase==='running'||s.pending)throw Error('Pause and finish the pending frame before changing reference automation.');
  await chrome.storage.local.set({[id]:checked});
 });};
 el('referenceFiles').onchange=e=>{const files=[...e.target.files];e.target.value='';if(files.length)op(()=>save(files));};
 el('chooseReferencePack').onclick=()=>el('referencePackFolder').click();
 el('referencePackFolder').onchange=e=>{const files=[...e.target.files];e.target.value='';if(files.length)op(async()=>{
  const s=await chrome.storage.local.get(['phase','pending','prompts','mappedPack']);
  if(s.phase==='running'||s.pending)throw Error('Pause and finish the pending frame before loading a reference pack.');
  if(!s.mappedPack||!s.prompts?.length)throw Error('Import one of the pack’s Frame ID / Prompt CSV files first.');
  const manifest=files.filter(f=>f.name==='Attachment_Manifest.csv');
  if(manifest.length!==1)throw Error('Choose the complete Aarohan_Reference_Pack folder, including Attachment_Manifest.csv and references.');
  const rows=StoryboardImport.csv(await manifest[0].text()),h=rows.shift(),id=h.indexOf('Frame ID'),refs=h.indexOf('Attach these actual files'),gap=h.indexOf('Reference gap');
  if(id<0||refs<0||gap<0)throw Error('Attachment manifest has incompatible headers.');
  const mapped=new Map();
  for(const row of rows){if(mapped.has(row[id]))throw Error('Duplicate frame in attachment manifest: '+row[id]);mapped.set(row[id],{files:(row[refs]||'').split(';').map(x=>x.trim()).filter(Boolean),gap:row[gap]||''});}
  const frameReferences=s.prompts.map(line=>{const label=line.split('||')[0].trim(),m=mapped.get(label);if(!m)throw Error('No attachment mapping for '+label);if(m.files.length>8||new Set(m.files).size!==m.files.length)throw Error('Invalid reference count for '+label);return m;});
  const needed=[...new Set(frameReferences.flatMap(m=>m.files))],assets={};
  for(const name of needed){
   if(!/^[\w -]+\.(png|jpg|jpeg|webp)$/i.test(name))throw Error('Invalid reference filename: '+name);
   const matches=files.filter(f=>f.name===name&&/\/references\//.test('/'+f.webkitRelativePath));
   if(matches.length!==1||matches[0].size>10_000_000||!['image/png','image/jpeg','image/webp'].includes(matches[0].type))throw Error('Missing, duplicate or unsupported image: '+name);
   assets[name]=await read(matches[0]);
  }
  for(const m of frameReferences)if(m.files.reduce((n,name)=>n+files.find(f=>f.name===name).size,0)>40_000_000)throw Error('A frame exceeds the 40 MB reference limit.');
  const live=await chrome.storage.local.get(['phase','pending','prompts']);
  if(live.phase==='running'||live.pending||JSON.stringify(live.prompts)!==JSON.stringify(s.prompts))throw Error('Queue changed while loading. Try again.');
  await chrome.storage.local.set({frameReferences,referencePackAssets:assets,referenceImages:[],referenceSummary:null,referenceSession:null,error:'',activity:`Mapped ${frameReferences.length} frames to ${needed.length} local reference images. Attach the current frame’s references before Start.`});
 });};
 el('attachReferences').onclick=()=>op(async()=>{
  const s=await chrome.storage.local.get(['frameReferences','index','referenceSummary','referencePackAssets','phase','pending']);
  const mapping=s.frameReferences?.[s.index||0];
  if(mapping&&s.referenceSummary?.mappingKey!==JSON.stringify(mapping)){
   if(s.phase==='running'||s.pending)throw Error('Pause and finish the pending frame first.');
   if(mapping.gap&&!confirm('This frame has a reference gap:\n'+mapping.gap+'\nContinue with only its mapped references?'))return;
   const images=mapping.files.map(name=>{const image=s.referencePackAssets?.[name];if(!image)throw Error('Load the reference pack folder again. Missing '+name);return image;});
   await chrome.storage.local.set({referenceImages:images,referenceSummary:{revision:uid(),names:mapping.files,mappingKey:JSON.stringify(mapping)},referenceSession:null});
   if(!images.length){await chrome.storage.local.set({activity:'No images mapped for this frame. Reference gap reviewed. Choose Start or Resume.'});return;}
  }
  await checkConnection();await send('ATTACH_REFERENCES');
 });
 el('confirmReferences').onclick=()=>op(()=>send('CONFIRM_REFERENCES'));
 el('clearReferences').onclick=()=>op(async()=>{const s=await chrome.storage.local.get(['phase','pending']);if(s.phase==='running'||s.pending)throw Error('Finish or reset the pending frame first.');await chrome.storage.local.remove(['referenceImages','referenceSummary','referenceSession']);});
 window.SmartFlowReferences={refresh,required};
 window.refresh().catch(showError);
})();

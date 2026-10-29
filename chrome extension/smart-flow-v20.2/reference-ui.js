// Reference images stay local until the employee explicitly attaches them.
(()=>{
 const el=id=>document.getElementById(id);
 const names=['Anaya Character Reference Sheet.png','Arjun Anime Character Reference Sheet.png','Mehak Character Reference Sheet.png','Trisha Anime Character Reference Sheet.png','Veer Anime Character Reference Sheet.png'];
 const required=s=>/REFERENCE SET REQUIRED:/.test(s.master||'');
 const read=file=>new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve({name:file.name,type:file.type,dataUrl:r.result});r.onerror=()=>reject(Error('Could not read '+file.name));r.readAsDataURL(file)});
 async function save(files){
  const s=await chrome.storage.local.get(['phase','pending']);
  if(s.phase==='running'||s.pending)throw Error('Finish or reset the pending frame before changing its references.');
  if(!files.length||files.length>8)throw Error('Choose between 1 and 8 character reference images.');
  if(files.some(f=>!['image/png','image/jpeg','image/webp'].includes(f.type)||f.size>10_000_000)||files.reduce((n,f)=>n+f.size,0)>40_000_000)throw Error('Use PNG, JPG or WebP references, under 10 MB each and 40 MB in total.');
  const images=await Promise.all(files.map(read));
  await chrome.storage.local.set({referenceImages:images,referenceSummary:{revision:uid(),names:images.map(f=>f.name)},referenceSession:null});
 }
 async function refresh(s){
  if(!el('referenceStatus'))return;
  const summary=s.referenceSummary,n=summary?.names?.length||0,session=s.referenceSession;
  el('referenceStatus').textContent=!n?(required(s)?'Required for this workbook: load all five Aarohan reference sheets before Start.':'Optional: choose character images to attach before your first frame.'):
    session?.revision===summary.revision?(session.state==='ready'?'References confirmed in ChatGPT. Start will include them with the first frame.':session.state==='sent'?'Reference images sent with the first frame. Keep using the same conversation.':'Upload requested. Check all attachments in ChatGPT, wait for upload to finish, then confirm below.'):
    `${n} references saved locally. Attach them to your ChatGPT conversation before Start.`;
  el('referenceNames').textContent=(summary?.names||[]).join(' · ');
  const locked=operationBusy||importBusy||s.phase==='running'||!!s.pending;
  for(const id of ['aarohanReferences','chooseReferences','referenceFiles','clearReferences'])el(id).disabled=locked;
  el('attachReferences').disabled=locked||!n;
  el('confirmReferences').hidden=!n||session?.state!=='attached';
  el('confirmReferences').disabled=locked;
  el('clearReferences').hidden=!n;
  el('referencePanel').classList.toggle('reference-required',required(s)&&!n);
  if(!['running','done'].includes(s.phase)&&(required(s)||n)&&!['ready','sent'].includes(session?.state))el('nextStep').textContent=!n?'Before Start: load the five Aarohan reference sheets below.':session?.state==='attached'?'Check all reference thumbnails in ChatGPT, wait for uploads to finish, then confirm them above.':'Before Start: attach your saved references to ChatGPT, then confirm the uploads.';
 }
 el('aarohanReferences').onclick=()=>op(async()=>{
  const files=await Promise.all(names.map(async name=>{const response=await fetch(chrome.runtime.getURL('character-references/'+name));if(!response.ok)throw Error('The packaged reference is missing: '+name);return new File([await response.blob()],name,{type:'image/png'});}));
  await save(files);
 });
 el('chooseReferences').onclick=()=>el('referenceFiles').click();
 el('referenceFiles').onchange=e=>{const files=[...e.target.files];e.target.value='';if(files.length)op(()=>save(files));};
 el('attachReferences').onclick=()=>op(async()=>{await checkConnection();await send('ATTACH_REFERENCES');});
 el('confirmReferences').onclick=()=>op(()=>send('CONFIRM_REFERENCES'));
 el('clearReferences').onclick=()=>op(async()=>{const s=await chrome.storage.local.get(['phase','pending']);if(s.phase==='running'||s.pending)throw Error('Finish or reset the pending frame first.');await chrome.storage.local.remove(['referenceImages','referenceSummary','referenceSession']);});
 window.SmartFlowReferences={refresh,required};
 window.refresh().catch(showError);
})();

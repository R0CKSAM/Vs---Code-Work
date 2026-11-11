const get=async()=> (await chrome.storage.local.get('job')).job;
const put=job=>chrome.storage.local.set({job});
const current=j=>j.dates[j.index];
const schedule=()=>chrome.alarms.create('next',{when:Date.now()+5000});
function datesBetween(start,end){
 const parse=s=>{if(!/^\d{4}-\d{2}-\d{2}$/.test(s))throw Error('Choose valid dates.');const d=new Date(s+'T00:00:00Z');if(!Number.isFinite(+d)||d.toISOString().slice(0,10)!==s)throw Error('Invalid date.');return d;};
 const a=parse(start),b=parse(end),n=Math.round((b-a)/86400000)+1;
 if(n<1||n>366)throw Error('Choose a range of 1–366 days.');
 return Array.from({length:n},(_,i)=>new Date(+a+i*86400000).toISOString().slice(0,10));
}
// Runs in the website's own context; calls exactly its existing PDF function.
async function sitePDF(date,city){
 const d=document.getElementById('TOIDate'),c=document.getElementById('TOICity'),b=document.querySelector('#TOIForm .btn-download');
 if(!d||!c||!b||typeof window.downloadTOIV3PDF!=='function')throw Error('Open the Times of India page and wait for it to load.');
 if(window.__induBatchBusy||b.disabled)throw Error('The website is already preparing a PDF. Wait before retrying.');
 if(![...c.options].some(o=>o.value===city))throw Error('City is no longer available.');
 window.__induBatchBusy=true;
 const original=window.alert;let issue='';
 window.alert=text=>{issue=String(text);console.warn('InduPaper download:',text);};
 try{
  d.value=date;c.value=city;
  d.dispatchEvent(new Event('change',{bubbles:true}));c.dispatchEvent(new Event('change',{bubbles:true}));
  await window.downloadTOIV3PDF();
  if(issue)throw Error(issue);
  return true;
 }finally{window.alert=original;window.__induBatchBusy=false;}
}
async function step(){
 const j=await get();if(!j||j.phase!=='queued')return;
 j.phase='preparing';j.error='';j.downloadId=null;j.since=Date.now();await put(j);
 try{
  const tab=await chrome.tabs.get(j.tabId);
  if(!/^https:\/\/(www\.)?indupaper\.com\/times-of-india\.html(?:[?#]|$)/.test(tab.url||''))throw Error('Return the original tab to the Times of India page.');
  const result=await chrome.scripting.executeScript({target:{tabId:j.tabId},world:'MAIN',func:sitePDF,args:[current(j),j.city]});
  if(!result[0]?.result)throw Error(result[0]?.error?.message||'Website did not finish preparing the PDF.');
  // Download events can arrive before executeScript resolves. Never overwrite newer state.
  const live=await get();if(live?.id!==j.id||live.index!==j.index)return;
  if(live.phase==='preparing'){live.phase='waiting';live.since=Date.now();await put(live);}
 }catch(e){const live=await get();if(live?.id===j.id&&live.index===j.index&&!['paused','done'].includes(live.phase)){live.phase='paused';live.error=String(e.message||e);await put(live);}}
}
async function bindDownload(item,suggest){
 const j=await get();if(!j||!['preparing','waiting'].includes(j.phase))return;
 const expected=`toi-${j.city}-${current(j)}.pdf`;
 if(item.byExtensionId&&item.byExtensionId!==chrome.runtime.id)return;
 if(item.filename.replace(/\\/g,'/').split('/').pop()!==expected)return;
 if(item.referrer&&!/^https:\/\/(www\.)?indupaper\.com\//.test(item.referrer))return;
 j.downloadId=item.id;j.phase='downloading';j.since=Date.now();await put(j);
 suggest({filename:`InduPaper/${j.city}/${expected}`,conflictAction:'uniquify'});
 // A small PDF may already be complete before listener storage finishes.
 const [actual]=await chrome.downloads.search({id:item.id});if(actual?.state==='complete')await finish(item.id);
}
chrome.downloads.onDeterminingFilename.addListener((item,suggest)=>{
 let answered=false;const answer=value=>{if(!answered){answered=true;suggest(value);}};
 bindDownload(item,answer).catch(console.error).finally(()=>answer());return true;
});
let finishing=false;
async function finish(id){
 if(finishing)return;finishing=true;
 try{const j=await get();if(!j||j.downloadId!==id||j.phase!=='downloading')return;
 j.history.push({date:current(j),status:'saved',downloadId:id});j.index++;j.downloadId=null;j.error='';
 j.phase=j.index>=j.dates.length?'done':j.pauseRequested?'paused':'queued';j.pauseRequested=false;
 await put(j);if(j.phase==='queued')await schedule();
 }finally{finishing=false;}
}
chrome.downloads.onChanged.addListener(async delta=>{
 if(delta.state?.current==='complete')await finish(delta.id);
 if(delta.state?.current==='interrupted'){const j=await get();if(j?.downloadId===delta.id){j.phase='paused';j.error='Download interrupted: '+(delta.error?.current||'check Chrome downloads');await put(j);}}
});
chrome.alarms.onAlarm.addListener(async alarm=>{
 if(alarm.name==='next')await step();
 if(alarm.name==='watch'){
  const j=await get();if(!j)return;
  if(j.phase==='downloading'){
   const [d]=await chrome.downloads.search({id:j.downloadId});if(d?.state==='complete'){await finish(d.id);return;}
  }
  if(['preparing','waiting','downloading'].includes(j.phase)&&Date.now()-j.since>10*60000){j.phase='paused';j.error='Timed out. Inspect the page and Chrome downloads before retrying to avoid duplicates.';await put(j);}
  if(j.phase==='queued')await step();
 }
});
chrome.alarms.create('watch',{periodInMinutes:1});
chrome.runtime.onMessage.addListener((m,s,reply)=>{
 (async()=>{
  let j=await get();
  if(m.action==='start'){
   if(j&&['queued','preparing','waiting','downloading'].includes(j.phase))throw Error('A batch is already active.');
   if(j&&j.phase==='paused'&&j.downloadId!==null)throw Error('Resolve the paused download before replacing this batch.');
   j={id:crypto.randomUUID(),tabId:m.tabId,city:m.city,dates:datesBetween(m.start,m.end),index:0,phase:'queued',downloadId:null,history:[],error:''};
   if(!/^[a-z0-9-]+$/i.test(j.city))throw Error('Choose a city.');await put(j);await schedule();
  }else if(m.action==='pause'&&j){
   if(j.phase==='queued')j.phase='paused';else if(['preparing','waiting','downloading'].includes(j.phase))j.pauseRequested=true;await put(j);
  }else if(m.action==='resume'&&j&&j.phase==='paused'){
   if(j.downloadId!=null){const [d]=await chrome.downloads.search({id:j.downloadId});if(d?.state==='in_progress')throw Error('Download is still running. Check Chrome downloads.');if(d?.state==='complete'){j.phase='downloading';await put(j);await finish(d.id);return;}}
   j.phase='queued';j.pauseRequested=false;j.error='';await put(j);await schedule();
  }else if(m.action==='skip'&&j&&j.phase==='paused'){
   if(j.downloadId!=null){const [d]=await chrome.downloads.search({id:j.downloadId});if(d?.state==='in_progress')throw Error('Wait for the active download before skipping.');}
   j.history.push({date:current(j),status:'skipped'});j.index++;j.downloadId=null;j.phase=j.index===j.dates.length?'done':'paused';j.error='';await put(j);
  }
 })().then(()=>reply({ok:true}),e=>reply({ok:false,error:e.message}));return true;
});

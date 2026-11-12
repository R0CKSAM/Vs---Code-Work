importScripts('page.js');
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
async function step(){
 const j=await get();if(!j||j.phase!=='queued')return;
 j.phase='preparing';j.error='';j.downloadId=null;j.since=Date.now();await put(j);
 try{
  const tab=await chrome.tabs.get(j.tabId);
  const url=new URL(tab.url);if(!/^https:$/.test(url.protocol)||!['indupaper.com','www.indupaper.com'].includes(url.hostname)||url.pathname!==(j.paper?.path||'/times-of-india.html'))throw Error('Return the original tab to the batch?s newspaper page.');
  const paper=j.paper||{path:'/times-of-india.html',dateId:'TOIDate',functionName:'downloadTOIV3PDF'};
  const selections=j.selections||[{id:'TOICity',value:j.city}];
  const result=await chrome.scripting.executeScript({target:{tabId:j.tabId},world:'MAIN',func:induPage,args:['download',{date:current(j),paper,selections}]});
  const answer=result[0]?.result;
  if(!answer?.ok)throw Error(answer?.error||result[0]?.error?.message||'Website execution ended before PDF creation completed. Inspect the newspaper tab before retrying.');
  // Download events can arrive before executeScript resolves. Never overwrite newer state.
  const live=await get();if(live?.id!==j.id||live.index!==j.index)return;
  if(live.phase==='preparing'){live.phase='waiting';live.since=Date.now();await put(live);}
 }catch(e){const live=await get();if(live?.id===j.id&&live.index===j.index&&['preparing','waiting'].includes(live.phase)){live.phase='paused';live.error=String(e.message||e);await put(live);}}
}
async function bindDownload(item,suggest){
 const j=await get();if(!j||!['preparing','waiting'].includes(j.phase))return;
 const legacy=!j.paper;
 const expected=legacy?`toi-${j.city}-${current(j)}.pdf`:`${j.paper.slug}-${j.editionSlug}-${current(j)}.pdf`;
 const leaf=item.filename.replace(/\\/g,'/').split('/').pop();
 if(item.byExtensionId&&item.byExtensionId!==chrome.runtime.id)return;
 if(legacy?leaf!==expected:!leaf.toLowerCase().endsWith('.pdf')||!leaf.includes(current(j)))return;
 if(item.referrer){try{const ref=new URL(item.referrer);if(!['indupaper.com','www.indupaper.com'].includes(ref.hostname)||ref.pathname!==(j.paper?.path||'/times-of-india.html'))return;}catch{return;}}
 j.downloadId=item.id;j.phase='downloading';j.since=Date.now();await put(j);
 suggest({filename:legacy?`InduPaper/${j.city}/${expected}`:`InduPaper/${j.paper.slug}/${j.editionSlug}/${expected}`,conflictAction:'uniquify'});
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
   const tab=await chrome.tabs.get(m.tabId),url=new URL(tab.url);
   if(url.protocol!=='https:'||!['indupaper.com','www.indupaper.com'].includes(url.hostname))throw Error('Open an InduPaper newspaper page.');
   const [inspection]=await chrome.scripting.executeScript({target:{tabId:m.tabId},world:'MAIN',func:induPage,args:['inspect']});
   if(!inspection?.result?.ok)throw Error(inspection?.result?.error||'Cannot read newspaper selectors.');
   const paper=inspection.result.paper;
   const selections=paper.fields.map(f=>{const value=m.selections?.find(s=>s.id===f.id)?.value;if(!value||!f.options.some(o=>o.value===value&&!o.disabled))throw Error('Choose a valid '+f.label+'.');return {id:f.id,value};});
   const edition=paper.fields.map(f=>f.options.find(o=>o.value===selections.find(s=>s.id===f.id).value).text).join(' / ')||'Main edition';
   const editionSlug=edition.toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'').slice(0,100)||'main';
   j={id:crypto.randomUUID(),tabId:m.tabId,paper,selections,edition,editionSlug,city:edition,dates:datesBetween(m.start,m.end),index:0,phase:'queued',downloadId:null,history:[],error:''};
   await put(j);await schedule();
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

importScripts('page.js');
const RETRY_DELAYS=[15000,45000,120000],ACTIVE=['queued','retrying','recovering','preparing','waiting','downloading'];
const get=async()=> (await chrome.storage.local.get('job')).job;
let changes=Promise.resolve(),stepping=false,reconciling=false,starting=false;
function edit(fn){const operation=changes.then(async()=>{const j=await get(),next=await fn(j);if(next)await chrome.storage.local.set({job:next});return next;});changes=operation.catch(()=>{});return operation;}
const current=j=>j.dates[j.index];
const same=(a,b)=>a&&b&&a.id===b.id&&a.index===b.index&&a.attemptId===b.attemptId;
const paperFor=j=>j.paper||{path:'/times-of-india.html',dateId:'TOIDate',functionName:'downloadTOIV3PDF'};
const belongs=(tab,j)=>{try{const u=new URL(tab.url);return u.protocol==='https:'&&['indupaper.com','www.indupaper.com'].includes(u.hostname)&&u.pathname===paperFor(j).path;}catch{return false;}};
const event=(j,text)=>{j.events=[...(j.events||[]),{at:Date.now(),date:current(j),text}].slice(-100);};
async function schedule(j,delay=5000){if(j&&['queued','retrying','recovering'].includes(j.phase))await chrome.alarms.create('next',{when:Math.max(Date.now()+500,j.nextAt||Date.now()+delay)});}
async function ensureWatch(){if(!await chrome.alarms.get('watch'))await chrome.alarms.create('watch',{periodInMinutes:1});}
function datesBetween(start,end){
 const parse=s=>{if(!/^\d{4}-\d{2}-\d{2}$/.test(s))throw Error('Choose valid dates.');const d=new Date(s+'T00:00:00Z');if(!Number.isFinite(+d)||d.toISOString().slice(0,10)!==s)throw Error('Invalid date.');return d;};
 const a=parse(start),b=parse(end),n=Math.round((b-a)/86400000)+1;
 if(n<1||n>366)throw Error('Choose a range of 1–366 days.');
 return Array.from({length:n},(_,i)=>new Date(+a+i*86400000).toISOString().slice(0,10));
}
function matchesDownload(item,j){
 const leaf=(item.filename||'').replace(/\\/g,'/').split('/').pop();
 if(item.byExtensionId&&item.byExtensionId!==chrome.runtime.id)return false;
 if(!leaf.toLowerCase().endsWith('.pdf')||!leaf.includes(current(j)))return false;
 if(!j.paper&&leaf!==`toi-${j.city}-${current(j)}.pdf`)return false;
 if(item.referrer){try{if(!belongs({url:item.referrer},j))return false;}catch{return false;}}
 return true;
}
async function downloaded(j){
 if(j.downloadId!=null){const found=await chrome.downloads.search({id:j.downloadId});if(found[0])return found[0];}
 if(!j.attemptAt)return null;
 const items=await chrome.downloads.search({startedAfter:new Date(j.attemptAt-2000).toISOString(),orderBy:['-startTime'],limit:250});
 const matches=items.filter(d=>matchesDownload(d,j));
 return matches.find(d=>d.state==='complete'&&d.exists!==false)||matches.find(d=>d.state==='in_progress')||matches[0]||null;
}
async function finish(id){
 const updated=await edit(j=>{
  if(!j||j.downloadId!==id||!['downloading','paused'].includes(j.phase))return;
  j.history.push({date:current(j),status:'saved',downloadId:id});j.index++;j.downloadId=null;
  j.attemptId=null;j.attemptAt=null;j.retryCount=0;j.resumeCount=0;j.nextAt=null;j.downloadBytes=null;j.lastProgressAt=null;j.error='';
  j.phase=j.index>=j.dates.length?'done':j.pauseRequested?'paused':'queued';j.pauseReason=j.pauseRequested?'user':null;j.pauseRequested=false;
  return j;
 });await schedule(updated);
}
async function failure(snapshot,answer){
 const updated=await edit(j=>{
  if(!same(j,snapshot)||!['preparing','waiting','recovering','downloading'].includes(j.phase))return;
  const message=String(answer.error||'The newspaper could not be downloaded.');
  if(j.pauseRequested){j.phase='paused';j.pauseReason='user';j.pauseRequested=false;j.error=message;return j;}
  if(answer.transient&&!answer.downloadRequested&&(j.retryCount||0)<RETRY_DELAYS.length){
   const delay=RETRY_DELAYS[j.retryCount||0];j.retryCount=(j.retryCount||0)+1;
   j.phase='retrying';j.nextAt=Date.now()+delay;j.downloadId=null;j.attemptId=null;
   j.error=message;event(j,`Automatic retry ${j.retryCount}/3 in ${delay/1000}s: ${message}`);
  }else{j.phase='paused';j.pauseReason=answer.downloadRequested?'uncertain':'error';j.error=message+(answer.downloadRequested?' Check Downloads before retrying; a PDF may already have been requested.':answer.transient?' Automatic retries exhausted.':'');}
  return j;
 });await schedule(updated);
}
async function findTab(j,create=false){
 try{const t=await chrome.tabs.get(j.tabId);if(belongs(t,j))return t;}catch{}
 const candidates=(await chrome.tabs.query({})).filter(t=>belongs(t,j));
 if(candidates.length>1)throw Error('Several tabs show this newspaper. Close the extra copies, then Resume.');
 let tab=candidates[0];
 if(!tab&&create)tab=await chrome.tabs.create({url:j.url||'https://www.indupaper.com'+paperFor(j).path,active:false});
 if(!tab)throw Error('Open the batch’s newspaper page, then Resume.');
 await edit(live=>{if(same(live,j)){live.tabId=tab.id;return live;}});return tab;
}
async function pageStatus(j,tab){
 const [r]=await chrome.scripting.executeScript({target:{tabId:tab.id},world:'MAIN',func:induPage,args:['status']});
 return r?.result;
}
async function step(){
 if(stepping)return;stepping=true;
 try{
  let j=await get();if(!j||!['queued','retrying','recovering'].includes(j.phase))return;
  if(j.nextAt&&Date.now()<j.nextAt){await schedule(j);return;}
  if(j.attemptId){const existing=await downloaded(j);if(existing?.state==='complete'||existing?.state==='in_progress'){await adopt(j,existing);return;}if(existing?.state==='interrupted'){await interrupted(j,existing);return;}}
  const tab=await findTab(j,!!j.restoreTab);const status=await pageStatus(j,tab);
  if(tab.status==='loading'||!status?.ready){
   const next=await edit(live=>{if(!same(live,j))return;live.readySince=live.readySince||Date.now();live.phase='recovering';live.nextAt=Date.now()+5000;live.activity='Waiting for newspaper controls to load.';if(Date.now()-live.readySince>120000){live.phase='paused';live.error='Newspaper controls did not load. Check the page and Resume.';}return live;});await schedule(next);return;
  }
  if(status.busy){const next=await edit(live=>{if(!same(live,j))return;live.phase='paused';live.error='The page is already preparing a PDF. Let it finish, then Resume.';return live;});return;}
  if(j.attemptId&&status.task?.id===j.attemptId&&status.task.downloadRequested){await edit(live=>{if(same(live,j)){live.phase='waiting';return live;}});return;}
  j=await edit(live=>{if(!same(live,j)||!['queued','retrying','recovering'].includes(live.phase))return;
   live.tabId=tab.id;live.phase='preparing';live.error='';live.downloadId=null;live.readySince=null;live.restoreTab=false;
   live.attemptId=crypto.randomUUID();live.attemptAt=live.since=Date.now();live.nextAt=null;live.downloadBytes=null;live.lastProgressAt=null;return live;
  });if(!j)return;
  try{
   const [r]=await chrome.scripting.executeScript({target:{tabId:j.tabId},world:'MAIN',func:induPage,args:['download',{date:current(j),paper:paperFor(j),selections:j.selections||[{id:'TOICity',value:j.city}],attemptId:j.attemptId}]});
   if(!r?.result?.ok){
    const live=await get();if(!same(live,j)||live.phase==='downloading')return;
    const d=await downloaded(live);if(d){await adopt(live,d);if(d.state==='complete'||d.state==='in_progress')return;}
    if(r?.result?.downloadRequested){await edit(next=>{if(same(next,j)&&next.phase==='preparing'){next.phase='waiting';next.since=Date.now();return next;}});return;}
    await failure(j,r?.result||{error:'Website execution ended before confirmation. Recovery will check Downloads.',downloadRequested:true});return;
   }
   await edit(live=>{if(same(live,j)&&live.phase==='preparing'){live.phase='waiting';live.since=Date.now();return live;}});
  }catch(e){await reconcile(false,String(e.message||e));}
 }catch(e){await edit(j=>{if(j&&['queued','retrying','recovering'].includes(j.phase)){j.phase='paused';j.pauseReason='page';j.error=String(e.message||e);return j;}});}
 finally{stepping=false;}
}
async function adopt(snapshot,item){
 const updated=await edit(j=>{if(!same(j,snapshot)||!ACTIVE.includes(j.phase))return;
  if(j.downloadId!==item.id||j.downloadBytes!==(item.bytesReceived||0))j.lastProgressAt=Date.now();
  j.downloadBytes=item.bytesReceived||0;j.lastProgressAt=j.lastProgressAt||Date.now();j.downloadId=item.id;j.phase='downloading';return j;
 });
 if(updated&&item.state==='complete'&&item.exists!==false)await finish(item.id);
 return updated;
}
async function interrupted(j,d){
 if(d.error==='USER_CANCELED'){await failure(j,{error:'Download canceled by the user.',transient:false});return;}
 if(d.canResume&&(j.resumeCount||0)<3){
  const updated=await edit(live=>{if(!same(live,j))return;live.phase='downloading';live.downloadId=d.id;live.resumeCount=(live.resumeCount||0)+1;live.since=Date.now();return live;});
  if(updated){try{await chrome.downloads.resume(d.id);return;}catch{}}
 }
 await failure(j,{error:'Download interrupted: '+(d.error||'connection lost'),transient:/^(NETWORK_|SERVER_FAILED|SERVER_UNREACHABLE|FILE_TRANSIENT_ERROR)/.test(d.error||'NETWORK_FAILED'),downloadRequested:false});
}
async function reconcile(startup=false,reason=''){
 if(reconciling)return;reconciling=true;
 try{
  let j=await get();if(!j||!ACTIVE.includes(j.phase))return;
  if(startup){j=await edit(live=>{if(same(live,j)&&ACTIVE.includes(live.phase)){live.restoreTab=true;return live;}});if(!j)return;}
  if(['queued','retrying','recovering'].includes(j.phase)){
   const next=await edit(live=>{if(same(live,j)){if(startup)live.restoreTab=true;return live;}});await schedule(next);return;
  }
  const d=await downloaded(j);
  if(d?.state==='complete'&&d.exists!==false){await adopt(j,d);return;}
  if(d?.state==='in_progress'){const tracked=await adopt(j,d);if(tracked&&Date.now()-tracked.lastProgressAt>10*60000)await failure(tracked,{error:'Download made no progress for ten minutes. Check Chrome Downloads.',downloadRequested:true});return;}
  if(d?.state==='interrupted'){await interrupted(j,d);return;}
  let tab;try{tab=await findTab(j,startup);}catch(e){await failure(j,{error:e.message});return;}
  let status;try{status=await pageStatus(j,tab);}catch{}
  const task=status?.task;
  if(status?.busy){
   if(Date.now()-j.since>10*60000)await failure(j,{error:'The page has been busy for ten minutes. Inspect it before continuing.',downloadRequested:true});return;
  }
  if(task&&task.id===j.attemptId&&task.state==='failed'){await failure(j,task.failure||{error:task.error,downloadRequested:task.downloadRequested});return;}
  if(task&&task.id===j.attemptId&&(task.downloadRequested||task.state==='complete')){
   if(Date.now()-j.since>60000)await failure(j,{error:'The page requested a PDF but Chrome has not confirmed it.',downloadRequested:true});return;
  }
  if(!status?.ready){
   const next=await edit(live=>{if(!same(live,j))return;live.phase='recovering';live.restoreTab=startup;live.nextAt=Date.now()+5000;return live;});await schedule(next);return;
  }
  // New page context after a restart/reload, with no matching download in Chrome history.
  await failure(j,{error:reason||'Browser/page restarted before the PDF was requested. Continuing the saved date.',transient:true,downloadRequested:false});
 }finally{reconciling=false;}
}
async function bindDownload(item,suggest){
 const snapshot=await get();if(!snapshot||!['preparing','waiting'].includes(snapshot.phase)||!matchesDownload(item,snapshot))return;
 const j=await edit(live=>{if(!same(live,snapshot)||!['preparing','waiting'].includes(live.phase))return;live.downloadId=item.id;live.phase='downloading';live.since=Date.now();return live;});if(!j)return;
 const expected=j.paper?`${j.paper.slug}-${j.editionSlug}-${current(j)}.pdf`:`toi-${j.city}-${current(j)}.pdf`;
 suggest({filename:j.paper?`InduPaper/${j.paper.slug}/${j.editionSlug}/${expected}`:`InduPaper/${j.city}/${expected}`,conflictAction:'uniquify'});
 const [actual]=await chrome.downloads.search({id:item.id});if(actual?.state==='complete')await finish(item.id);
}
chrome.downloads.onDeterminingFilename.addListener((item,suggest)=>{let answered=false;const answer=x=>{if(!answered){answered=true;suggest(x);}};bindDownload(item,answer).catch(console.error).finally(()=>answer());return true;});
chrome.downloads.onChanged.addListener(async delta=>{
 if(delta.state?.current==='complete')await finish(delta.id);
 if(delta.state?.current==='interrupted'){const j=await get();if(j?.downloadId===delta.id&&j.phase==='downloading'){const [d]=await chrome.downloads.search({id:delta.id});if(d)await interrupted(j,d);}}
});
chrome.alarms.onAlarm.addListener(async a=>{if(a.name==='next')await step();if(a.name==='watch')await reconcile();});
chrome.runtime.onStartup.addListener(async()=>{await ensureWatch();await reconcile(true);});
chrome.runtime.onInstalled.addListener(async()=>{await ensureWatch();await reconcile(true);});
ensureWatch().catch(console.error);
chrome.runtime.onMessage.addListener((m,s,reply)=>{
 (async()=>{
  await ensureWatch();let j=await get();
  if(m.action==='start'){
   if(starting||j&&ACTIVE.includes(j.phase))throw Error('A batch is already active.');starting=true;
   try{
    if(j?.phase==='paused'&&j.downloadId!=null)throw Error('Resolve the paused download before replacing this batch.');
    const tab=await chrome.tabs.get(m.tabId),url=new URL(tab.url);
    if(url.protocol!=='https:'||!['indupaper.com','www.indupaper.com'].includes(url.hostname))throw Error('Open an InduPaper newspaper page.');
    const [r]=await chrome.scripting.executeScript({target:{tabId:m.tabId},world:'MAIN',func:induPage,args:['inspect']});if(!r?.result?.ok)throw Error(r?.result?.error||'Cannot read newspaper selectors.');
    const paper=r.result.paper,selections=paper.fields.map(f=>{const value=m.selections?.find(x=>x.id===f.id)?.value;if(!value||!f.options.some(o=>o.value===value&&!o.disabled))throw Error('Choose a valid '+f.label+'.');return {id:f.id,value};});
    const edition=paper.fields.map(f=>f.options.find(o=>o.value===selections.find(x=>x.id===f.id).value).text).join(' / ')||'Main edition';
    const editionSlug=edition.toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'').slice(0,100)||'main';
    j={id:crypto.randomUUID(),tabId:m.tabId,url:url.origin+url.pathname,paper,selections,edition,editionSlug,city:edition,dates:datesBetween(m.start,m.end),index:0,phase:'queued',downloadId:null,history:[],events:[],error:'',retryCount:0};
    const created=await edit(live=>{if(live&&ACTIVE.includes(live.phase))throw Error('A batch became active.');return j;});await schedule(created);
   }finally{starting=false;}
  }else if(m.action==='pause'){
   await edit(live=>{if(!live)return;if(['queued','retrying','recovering'].includes(live.phase)){live.phase='paused';live.pauseReason='user';live.nextAt=null;}else if(['preparing','waiting','downloading'].includes(live.phase))live.pauseRequested=true;return live;});
  }else if(m.action==='resume'&&j?.phase==='paused'){
   const d=await downloaded(j);
   if(d?.state==='complete'&&d.exists!==false){await edit(live=>{if(same(live,j)){live.downloadId=d.id;live.phase='downloading';live.pauseRequested=false;return live;}});await finish(d.id);return;}
   if(d?.state==='in_progress'){await edit(live=>{if(same(live,j)){live.downloadId=d.id;live.phase='downloading';live.pauseRequested=false;return live;}});return;}
   const next=await edit(live=>{if(!same(live,j))return;live.phase='queued';live.restoreTab=true;live.pauseRequested=false;live.pauseReason=null;live.error='';live.retryCount=0;live.nextAt=null;live.downloadId=null;live.attemptId=null;live.attemptAt=null;return live;});await schedule(next);
  }else if(m.action==='skip'&&j&&['paused','retrying'].includes(j.phase)){
   const d=await downloaded(j);if(d?.state==='in_progress')throw Error('Wait for the active download before skipping.');
   const next=await edit(live=>{if(!same(live,j))return;live.history.push({date:current(live),status:'skipped',reason:live.error||'Skipped by user'});live.index++;live.downloadId=null;live.attemptId=null;live.attemptAt=null;live.retryCount=0;live.resumeCount=0;live.nextAt=null;live.phase=live.index>=live.dates.length?'done':'queued';live.pauseRequested=false;live.error='';return live;});await schedule(next);
  }
 })().then(()=>reply({ok:true}),e=>reply({ok:false,error:e.message}));return true;
});

chrome.runtime.onMessage.addListener((msg,sender,sendResponse)=>{if(msg.action==='MY_TAB_ID')sendResponse({tabId:sender.tab?.id??null});});
// Keep a bounded local log of queue state changes. Never include the prompt text.
let logWrite=false;
chrome.storage.onChanged.addListener(async(changes,area)=>{
 if(area!=='local'||logWrite)return;
 const tracked=['phase','index','error','pending'];if(!tracked.some(k=>changes[k]))return;
 const state=await chrome.storage.local.get(['diagnosticEvents','phase','index','error','pending']);
 const old=changes.pending?.oldValue,newp=changes.pending?.newValue;
 const event={time:new Date().toISOString(),phase:state.phase||'idle',index:state.index||0,pendingState:state.pending?.state||null,error:String(state.error||'').slice(0,300)};
 if(old?.state===newp?.state && !changes.phase && !changes.index && !changes.error)return;
 const events=(state.diagnosticEvents||[]).slice(-298);events.push(event);
 logWrite=true;try{await chrome.storage.local.set({diagnosticEvents:events})}finally{logWrite=false}
});
// Export completed images only when explicitly opted in. Browser manages download permission.
chrome.runtime.onMessage.addListener((msg,sender,sendResponse)=>{
 if(msg.action!=='SAVE_FRAME_IMAGE')return;
 (async()=>{
  const s=await chrome.storage.local.get(['ownerTabId','autoDownload','queueId','queueMode']);
  if(!s.autoDownload)throw Error('Automatic downloads disabled.');
  if(sender.tab?.id!==s.ownerTabId)throw Error('Download rejected: wrong ChatGPT tab.');
  if(msg.queueId&&msg.queueId!==s.queueId)throw Error('Download rejected: the queue changed.');
  if(typeof msg.dataUrl!=='string'||!/^data:image\/(png|jpeg|webp);base64,/.test(msg.dataUrl)||msg.dataUrl.length>25_000_000)throw Error('Unsupported image data.');
  const name=String(msg.fileName||'Frame').replace(/[^a-zA-Z0-9_-]/g,'_').slice(0,90);
  const mime=msg.dataUrl.match(/^data:image\/(png|jpeg|webp);base64,/)[1];
  const ext=mime==='jpeg'?'jpg':mime;
  return await chrome.downloads.download({url:msg.dataUrl,filename:`Storyboard Studio/${name}.${ext}`,conflictAction:'uniquify',saveAs:false});
 })().then(id=>sendResponse({ok:true,id})).catch(e=>sendResponse({ok:false,error:String(e.message||e)}));return true;
});
// Repeat mode observes Chrome's actual download state before advancing.
chrome.runtime.onMessage.addListener((msg,sender,sendResponse)=>{
 if(msg.action!=='FRAME_DOWNLOAD_STATUS')return;
 (async()=>{
  const s=await chrome.storage.local.get(['ownerTabId','pending','queueId']);
  if(sender.tab?.id!==s.ownerTabId||msg.queueId!==s.queueId||msg.id!==s.pending?.downloadId)throw Error('Download check rejected: wrong tab or pending image.');
  const [item]=await chrome.downloads.search({id:msg.id});
  if(!item)return {state:'interrupted',error:'Download was removed from Chrome history.'};
  if(item.state==='complete'&&item.exists===false)return {state:'interrupted',error:'The downloaded file was removed.'};
  return {state:item.state,error:item.error||''};
 })().then(result=>sendResponse({ok:true,...result})).catch(e=>sendResponse({ok:false,error:String(e.message||e)}));return true;
});
// Notify once on transition to done. No external service is used.
chrome.storage.onChanged.addListener((changes,area)=>{
 if(area!=='local'||changes.phase?.newValue!=='done'||changes.phase?.oldValue==='done')return;
 chrome.storage.local.get(['completionNotifications','prompts']).then(s=>{
  if(!s.completionNotifications)return;
  chrome.notifications.create('storyboard-finished-'+Date.now(),{type:'basic',iconUrl:'icon128.png',title:'Storyboard complete',message:`Finished ${s.prompts?.length||0} storyboard frames.`}).catch(()=>{});
 });
});

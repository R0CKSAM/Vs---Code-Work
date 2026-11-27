chrome.action.onClicked.addListener(async () => {
  const url = chrome.runtime.getURL('workspace.html');
  const existing = (await chrome.tabs.query({})).find(t => t.url === url);
  if (existing) { await chrome.tabs.update(existing.id, {active:true}); await chrome.windows.update(existing.windowId, {focused:true}); }
  else await chrome.tabs.create({url});
});

chrome.runtime.onInstalled.addListener(async()=>{
 for(const tab of await chrome.tabs.query({url:['https://chatgpt.com/*','https://chat.openai.com/*']}))try{
  await chrome.scripting.executeScript({target:{tabId:tab.id},func:()=>{window.__smartBannerGen=false;}});
  await chrome.scripting.executeScript({target:{tabId:tab.id},files:['content.js']});
 }catch{}
});
chrome.runtime.onMessage.addListener((m,s,reply)=>{
 if(m.type==='BANNER_ARM_DOWNLOAD'&&s.tab&&/^https:\/\/(chatgpt\.com|chat\.openai\.com)\//.test(s.url||'')){
  if(!m.name||!/^.+\.(png|jpe?g|webp|avif)$/i.test(m.name)||/[\\/]/.test(m.name)){reply({ok:false,error:'Unsupported image filename'});return;}
  chrome.scripting.executeScript({target:{tabId:s.tab.id},world:'MAIN',func:capturePageDownload,args:[m.name]})
   .then(([r])=>reply(r?.result||{ok:false,error:'No download result'}),e=>reply({ok:false,error:e.message}));return true;
 }
 if(s.url!==chrome.runtime.getURL('workspace.html'))return;
 if(m.type==='POWER'){if(m.on)chrome.power.requestKeepAwake('system');else chrome.power.releaseKeepAwake();reply({ok:true});}
});
function capturePageDownload(expectedName){
 return new Promise(resolve=>{
  if(window.__smartBannerFileCapture){resolve({ok:false,error:'Another file capture is active'});return;}
  window.__smartBannerFileCapture=true;
  const blobs=new Map(),originalURL=URL.createObjectURL,originalClick=HTMLAnchorElement.prototype.click,originalDispatch=HTMLAnchorElement.prototype.dispatchEvent;
  let finished=false,timer;
  function cleanup(){
   clearTimeout(timer);document.removeEventListener('click',onClick,true);
   if(URL.createObjectURL===createURL)URL.createObjectURL=originalURL;
   if(HTMLAnchorElement.prototype.click===click)HTMLAnchorElement.prototype.click=originalClick;
   if(HTMLAnchorElement.prototype.dispatchEvent===dispatch)HTMLAnchorElement.prototype.dispatchEvent=originalDispatch;
   delete window.__smartBannerFileCapture;blobs.clear();
  }
  function finish(result){if(finished)return;finished=true;cleanup();resolve(result);}
  function createURL(blob){const url=originalURL.call(URL,blob);blobs.set(url,blob);return url;}
  function capture(anchor){
   if(finished||!anchor||anchor.download?.toLowerCase()!==expectedName.toLowerCase())return false;
   const blob=blobs.get(anchor.href);if(!blob)return false;
   if(blob.size>30*1024*1024){finish({ok:false,error:'Image exceeds 30 MB'});return true;}
   const reader=new FileReader();reader.onload=()=>finish({ok:true,dataUrl:reader.result});reader.onerror=()=>finish({ok:false,error:'Could not read image Blob'});reader.readAsDataURL(blob);return true;
  }
  function click(){if(!capture(this))return originalClick.call(this);}
  function dispatch(event){if(event.type==='click'&&capture(this))return true;return originalDispatch.call(this,event);}
  function onClick(event){if(capture(event.target?.closest?.('a[download]'))){event.preventDefault();event.stopImmediatePropagation();}}
  URL.createObjectURL=createURL;HTMLAnchorElement.prototype.click=click;HTMLAnchorElement.prototype.dispatchEvent=dispatch;
  document.addEventListener('click',onClick,true);
  timer=setTimeout(()=>finish({ok:false,error:'ChatGPT did not provide the expected file Blob within 30 seconds'}),30000);
 });
}

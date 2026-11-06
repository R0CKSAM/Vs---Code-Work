// Actual unpacked extension, Chrome storage and downloads. ChatGPT document is
// fulfilled locally so generated prompts never reach the real ChatGPT service.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
const referenceRun=process.argv.includes('--references');
const mappedRun=process.argv.includes('--mapped-pack');
const autoRun=process.argv.includes('--auto-references');
const requestRun=process.argv.includes('--reference-request');
const root=fileURLToPath(new URL('../',import.meta.url));
const out=path.resolve(root,requestRun?'../../Smart-Flow-Reference-Recovery-Audit-20261106':autoRun?'../../Smart-Flow-Auto-References-Audit-20261106':mappedRun?'../../Smart-Flow-Mapped-Pack-Audit-20261106':referenceRun?'../../Smart-Flow-References-Audit-20261029':'../../Smart-Flow-Audit-20261029');fs.mkdirSync(out,{recursive:true});
const profile=fs.mkdtempSync(path.join(os.tmpdir(),'smart-flow-installed-'));
fs.mkdirSync(path.join(profile,'Default'));fs.writeFileSync(path.join(profile,'Default','Preferences'),JSON.stringify({download:{default_directory:out,prompt_for_download:false,directory_upgrade:true}}));
const chrome=spawn('C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',['--headless=new','--disable-gpu','--no-first-run','--enable-unsafe-extension-debugging','--enable-automation','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{stdio:'ignore',windowsHide:true});
let socket,checks=0;
const check=(ok,name)=>{assert(ok,name);checks++;};
const pause=ms=>new Promise(r=>setTimeout(r,ms));
const until=async(fn,label,timeout=25000)=>{const start=Date.now();while(Date.now()-start<timeout){const value=await fn();if(value)return value;await pause(75);}throw Error('Timed out: '+label);};
try{
 const portFile=path.join(profile,'DevToolsActivePort');const portText=await until(()=>{try{const text=fs.readFileSync(portFile,'utf8');return text.includes('\n')&&text;}catch{return false;}},'browser startup');const [port,endpoint]=portText.trim().split('\n');
 socket=new WebSocket('ws://127.0.0.1:'+port+endpoint.trim());await new Promise((r,j)=>{socket.onopen=r;socket.onerror=j;});
 let next=0;const pending=new Map(),events=[];
 socket.onmessage=e=>{const m=JSON.parse(e.data);if(!m.id){for(const fn of events)fn(m);return;}const p=pending.get(m.id);if(!p)return;pending.delete(m.id);clearTimeout(p.timer);m.error?p.reject(Error(m.error.message)):p.resolve(m.result);};
 const call=(method,params={},sessionId)=>new Promise((resolve,reject)=>{const id=++next,timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout '+method));},25000);pending.set(id,{resolve,reject,timer});socket.send(JSON.stringify({id,method,params,sessionId}));});
 const evaluate=async(s,expression)=>{const r=await call('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true,userGesture:true},s);if(r.exceptionDetails)throw Error(r.exceptionDetails.exception?.description||r.exceptionDetails.text);return r.result.value;};
 const attach=async id=>(await call('Target.attachToTarget',{targetId:id,flatten:true})).sessionId;
 const id=(await call('Extensions.loadUnpacked',{path:root})).id;check(!!id,'Actual extension loads unpacked');
 const chatTarget=await call('Target.createTarget',{url:'about:blank'}),chat=await attach(chatTarget.targetId);
 const pixel='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6WQAAAABJRU5ErkJggg==';
 const fixture=`<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none';script-src 'unsafe-inline';style-src 'unsafe-inline';img-src data:;connect-src data:"><style>body{font:16px sans-serif;margin:40px}textarea{width:700px;height:200px}button{padding:15px}img{width:64px;height:64px}form{padding:15px}</style></head><body><h1>Local Smart Flow acceptance fixture</h1><div id="conversation"></div><form><input id="chat-files" type="file" accept="image/*" multiple><div id="attachments"></div><textarea id="prompt-textarea"></textarea><button type="submit" aria-label="Send">Send</button></form><div id="generation"></div><script>
 window.sent=[];window.outputs=0;window.uploads=[];document.getElementById('chat-files').addEventListener('change',e=>{uploads.push([...e.target.files].map(f=>({name:f.name,size:f.size,type:f.type})));const cards=document.getElementById('attachments');cards.replaceChildren();const progress=document.createElement('span');progress.setAttribute('role','progressbar');progress.textContent='Uploading';cards.append(progress);for(const f of e.target.files){const img=document.createElement('img');img.alt=f.name;img.src=${JSON.stringify(pixel)}+'#reference-'+f.name;cards.append(img);}setTimeout(()=>progress.remove(),300);});document.querySelector('form').addEventListener('submit',e=>{e.preventDefault();const editor=document.querySelector('textarea'),text=editor.value;if(!text)return;sent.push(text);const user=document.createElement('div');user.dataset.messageAuthorRole='user';user.dataset.messageId='user-'+sent.length;user.textContent=text;document.querySelector('#conversation').append(user);editor.value='';document.getElementById('attachments').replaceChildren();document.getElementById('chat-files').value='';document.querySelector('#generation').innerHTML='<button aria-label="Stop generating">Stop</button>';setTimeout(()=>{document.querySelector('#generation').replaceChildren();if(${JSON.stringify(requestRun)}&&sent.length===1){const request=document.createElement('div');request.dataset.messageAuthorRole='assistant';request.dataset.messageId='reference-request-1';request.textContent='Please attach the Rhea reference image. I already have the festival location reference.';document.querySelector('#conversation').append(request);return;}outputs++;const a=document.createElement('div');a.dataset.messageAuthorRole='assistant';a.dataset.messageId='assistant-'+outputs;const b=document.createElement('button');b.type='button';b.dataset.testid='generated-image-preview';b.setAttribute('aria-label','Generated image '+outputs);const img=document.createElement('img');img.src='data:image/png;base64,'+btoa(atob(${JSON.stringify(pixel)}.split(',')[1])+String(outputs));b.append(img);a.append(b);document.querySelector('#conversation').append(a);},1200);});</script></body></html>`;
 await call('Fetch.enable',{patterns:[{urlPattern:'https://chatgpt.com/c/smart-flow-local-audit*',resourceType:'Document',requestStage:'Request'}]},chat);
 events.push(m=>{if(m.sessionId===chat&&m.method==='Fetch.requestPaused')call('Fetch.fulfillRequest',{requestId:m.params.requestId,responseCode:200,responseHeaders:[{name:'Content-Type',value:'text/html; charset=utf-8'}],body:Buffer.from(fixture).toString('base64')},chat).catch(console.error);});
 await call('Page.navigate',{url:'https://chatgpt.com/c/smart-flow-local-audit'},chat);
 await until(()=>evaluate(chat,'!!document.getElementById("prompt-textarea")'),'local ChatGPT fixture');
 const popupTarget=await call('Target.createTarget',{url:`chrome-extension://${id}/popup.html`}),popup=await attach(popupTarget.targetId);
 await until(()=>evaluate(popup,'typeof importFile==="function"&&!!document.getElementById("nextStep")'),'actual popup startup');
 await call('Target.activateTarget',{targetId:chatTarget.targetId});
 await call('Browser.setDownloadBehavior',{behavior:'default',eventsEnabled:true});
 await call('Emulation.setDeviceMetricsOverride',{width:370,height:570,deviceScaleFactor:1,mobile:false},popup);
 await evaluate(popup,'document.getElementById("checkConnection").click()');
 await until(()=>evaluate(popup,'document.getElementById("connectionStatus").textContent.includes("Connected")'),'actual content-script handshake');check(true,'Actual popup connects to actual isolated content script');
 if(mappedRun){
  await evaluate(popup,'chrome.storage.local.set({autoReferences:'+autoRun+'})');
  const pack=process.argv[process.argv.indexOf('--mapped-pack')+1];
  if(!pack||!fs.existsSync(pack))throw Error('Pass the reference pack directory after --mapped-pack.');
  const setFiles=async(selector,files)=>{const {root:doc}=await call('DOM.getDocument',{},popup);const {nodeId}=await call('DOM.querySelector',{nodeId:doc.nodeId,selector},popup);await call('DOM.setFileInputFiles',{nodeId,files},popup);await evaluate(popup,'document.querySelector('+JSON.stringify(selector)+').dispatchEvent(new Event("change"))');};
  await setFiles('#file',[path.join(pack,'S01_First_5_Test.csv')]);
  await until(()=>evaluate(popup,'!importBusy&&chrome.storage.local.get("mappedPack").then(s=>s.mappedPack)'),'mapped CSV import');
  // Headless CDP does not enumerate webkitdirectory inputs. Use real OS-backed
  // Files through the ordinary input and emulate only directory-relative metadata.
  await evaluate(popup,'{const input=document.getElementById("referencePackFolder");window.packChange=input.onchange;input.onchange=null;input.removeAttribute("webkitdirectory");}');
  await setFiles('#referencePackFolder',fs.readdirSync(pack,{recursive:true}).map(n=>path.join(pack,n)).filter(n=>fs.statSync(n).isFile()));
  await evaluate(popup,'{const input=document.getElementById("referencePackFolder");for(const f of input.files)Object.defineProperty(f,"webkitRelativePath",{value:"Aarohan_Reference_Pack/"+(f.name.endsWith(".png")?"references/":"")+f.name});input.onchange=window.packChange;input.dispatchEvent(new Event("change"));}');
  try{await until(()=>evaluate(popup,'!operationBusy&&chrome.storage.local.get("frameReferences").then(s=>s.frameReferences?.length===5)'),'actual directory input and mapping');}catch(e){console.log(await evaluate(popup,'({alert:document.getElementById("alert").textContent,busy:operationBusy,files:[...document.getElementById("referencePackFolder").files].map(f=>({name:f.name,path:f.webkitRelativePath,type:f.type}))})'));throw e;}
  const stored=await evaluate(popup,'chrome.storage.local.get(["referencePackAssets","frameReferences"]).then(s=>({names:Object.keys(s.referencePackAssets),first:s.frameReferences[0]}))');
  check(stored.names.length===fs.readdirSync(path.join(pack,'references')).filter(n=>/\.(png|jpe?g|webp)$/i.test(n)).length&&stored.first.files[0]==='LOC_FESTIVAL.png','Actual folder input indexes all fourteen originals');
  if(autoRun){
   await evaluate(popup,'refresh()');
   check(await evaluate(popup,'document.getElementById("autoReferences").checked'),'Automatic references enabled in UI');
   await evaluate(popup,'document.getElementById("allowReferenceGaps").click()');await until(()=>evaluate(popup,'!operationBusy'),'gap preference');
   await evaluate(popup,'document.getElementById("autoDownload").click();document.getElementById("start").click()');
   try{await until(()=>evaluate(popup,'chrome.storage.local.get("phase").then(s=>s.phase==="done")'),'five automatic scenes and downloads',160000);}catch(e){console.log(await evaluate(popup,'chrome.storage.local.get(["phase","error","activity","index"])')); throw e;}
   const uploads=await evaluate(chat,'uploads'),sent=await evaluate(chat,'sent');
   const sceneMessages=sent.filter(text=>text.startsWith('Frame: '));
   check(sent.length===(requestRun?6:5)&&sceneMessages.length===5&&sceneMessages.every((text,i)=>text.includes('Frame: S01_F00'+(i+1))&&text.includes('REFERENCE GUIDE:')),'All five scene prompts send in original order with reference instructions');
   if(requestRun){check(uploads.length===5&&uploads[1].length===1&&uploads[1][0].name==='CAST_SUPPORT.png','Requested Rhea reference is found outside the initial frame mapping');check(sent[1].includes('Continue ONLY the pending S01_F001')&&!sent[1].startsWith('Frame: '),'Recovery continues the same frame without resending its original prompt');}
   check(requestRun?uploads.length===5:uploads.length===4&&uploads[0].length===1&&uploads[1].length===3&&uploads[2].length===1&&uploads[3].length===1,'Reference changes upload automatically; unchanged set is reused');
   check(uploads.flat().every(f=>f.size===fs.statSync(path.join(pack,'references',f.name)).size),'All automatically uploaded files preserve full source size');
   const state=await evaluate(popup,'chrome.storage.local.get(["index","frameHistory","pending"])');check(state.index===5&&state.pending===null&&state.frameHistory.filter(f=>f.status==="completed").length===5,'Five automatic downloads complete with history');
   const files=fs.readdirSync(out,{recursive:true}).filter(n=>/S01_F00[1-5].*\.png$/.test(n));check(files.length>=5&&files.every(f=>fs.statSync(path.join(out,f)).size>0),'All five downloaded images exist on disk');
  }else{
  await evaluate(popup,'document.getElementById("attachReferences").click()');
  await until(()=>evaluate(chat,'uploads.length===1'),'first actual reference upload');
  const uploaded=await evaluate(chat,'uploads[0]');check(uploaded.length===1&&uploaded[0].name==='LOC_FESTIVAL.png'&&uploaded[0].size===fs.statSync(path.join(pack,'references','LOC_FESTIVAL.png')).size,'Actual File matches full-resolution mapped reference');
  await until(()=>evaluate(popup,'!operationBusy'),'attachment finishes');
  await evaluate(popup,'document.getElementById("confirmReferences").click()');await until(()=>evaluate(popup,'!operationBusy'),'confirmation finishes');
  await evaluate(popup,'document.getElementById("autoDownload").click();document.getElementById("start").click()');
  await until(()=>evaluate(popup,'chrome.storage.local.get(["phase","index"]).then(s=>s.phase==="paused"&&s.index===1)'),'first frame saved and reference-change pause',35000);
  check(await evaluate(chat,'sent.length===1&&sent[0].includes("Frame: S01_F001")&&sent[0].includes("LOC_FESTIVAL.png")'),'Only first frame sent before reference-change pause');
  const files=fs.readdirSync(out,{recursive:true}).filter(n=>n.endsWith('.png')&&n.includes('S01_F001'));check(files.length>0&&files.some(f=>fs.statSync(path.join(out,f)).size>0),'Actual Chrome image download completed');
  await evaluate(popup,'refresh()');
  await evaluate(popup,'document.getElementById("attachReferences").click()');await until(()=>evaluate(chat,'uploads.length===2'),'second mapped reference upload');
  const second=await evaluate(chat,'uploads[1]');check(second.length===3&&second.every(f=>f.size===fs.statSync(path.join(pack,'references',f.name)).size),'Second frame receives exact character, location and prop originals');
  await evaluate(popup,'refresh()');
  }
  const width=await evaluate(popup,'({body:document.body.scrollWidth,app:document.querySelector(".app").scrollWidth})');check(width.body<=370&&width.app<=370,'Mapped reference UI fits popup');
  const {data}=await call('Page.captureScreenshot',{format:'png'},popup);fs.writeFileSync(path.join(out,'mapped-pack-paused.png'),Buffer.from(data,'base64'));
  const report={status:'PASS',checks,realUnpackedExtension:true,realOSFiles:true,directoryRelativeMetadataEmulated:true,fullResolutionFiles:true,actualChromeDownload:true,syntheticChatGPTOnly:true,liveImageCreditsUsed:0,automaticReferenceRun:autoRun,requestedReferenceRecovery:requestRun};
  fs.writeFileSync(path.join(out,'installed-mapped-pack-results.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
 }else{
 const oldWorkbook='Y:\\Veto Logs Backup\\Aarohan\\Smart Flow Uploads\\1.1_Smart_Flow_UPLOAD.xlsx';
 const workbook=referenceRun?path.join(path.dirname(oldWorkbook),'Aarohan_1.1_1.2_Character_Batches_Smart_Flow_WITH_REFERENCES.xlsx'):oldWorkbook;
 if(!fs.existsSync(workbook))throw Error('User workbook unavailable for acceptance');
 const {root:doc}=await call('DOM.getDocument',{},popup);const {nodeId}=await call('DOM.querySelector',{nodeId:doc.nodeId,selector:'#file'},popup);
 await call('DOM.setFileInputFiles',{nodeId,files:[workbook]},popup);await evaluate(popup,'document.getElementById("file").dispatchEvent(new Event("change"))');
 await until(()=>evaluate(popup,'!importBusy&&document.getElementById("loaded").textContent.includes("'+(referenceRun?227:110)+'")'),'workbook upload');
 check(await evaluate(popup,'!document.getElementById("start").disabled'),'Start enabled immediately after real XLSX input');
 if(referenceRun){
  const attempt=async()=>{await evaluate(popup,'document.getElementById("start").click()');await until(()=>evaluate(popup,'!operationBusy'),'start validation');};
  await attempt();check(await evaluate(chat,'sent.length===0'),'Required workbook cannot start without character references');
  check(await evaluate(popup,'document.getElementById("alert").textContent.includes("requires character images")'),'Missing reference error explains the next action');
  await evaluate(popup,'document.getElementById("aarohanReferences").click()');
  await until(()=>evaluate(popup,'!operationBusy&&chrome.storage.local.get("referenceSummary").then(s=>s.referenceSummary?.names?.length===5)'),'load five full-resolution reference sheets');
  const saved=await evaluate(popup,'chrome.storage.local.get(["referenceImages","referenceSummary"]).then(s=>({names:s.referenceSummary.names,sizes:s.referenceImages.map(i=>i.dataUrl.length),count:s.referenceImages.length}))');
  check(saved.count===5&&saved.sizes.every(n=>n>2000000),'Full-resolution originals are saved, without resizing');
  check(await evaluate(chat,'uploads.length===0&&sent.length===0'),'Loading local reference pack sends nothing to ChatGPT');
  await attempt();check(await evaluate(chat,'sent.length===0'),'Saved references alone cannot bypass attachment confirmation');
  await evaluate(popup,'document.getElementById("attachReferences").click()');
  await until(()=>evaluate(chat,'uploads.length===1&&uploads[0].length===5'),'actual File input receives all five references');
  await until(()=>evaluate(popup,'!operationBusy'),'attachment operation finishes');
  const uploaded=await evaluate(chat,'uploads[0]');
  check(uploaded.every(f=>f.size===fs.statSync(path.join(root,'character-references',f.name)).size),'Actual attached File sizes exactly match source PNG files');
  check(await evaluate(chat,'sent.length===0'),'Attaching images does not submit or generate');
  await attempt();check(await evaluate(chat,'sent.length===0'),'Unconfirmed attachment request cannot start generation');
  check(await evaluate(popup,'!document.getElementById("confirmReferences").hidden'),'Upload confirmation is clearly visible');
  await evaluate(popup,'document.getElementById("attachReferences").click()');await until(()=>evaluate(popup,'!operationBusy'),'duplicate attach guard');
  check(await evaluate(chat,'uploads.length===1'),'Repeated attach does not upload duplicates');
  await evaluate(popup,'document.getElementById("confirmReferences").click()');
  await until(()=>evaluate(popup,'!operationBusy&&chrome.storage.local.get("referenceSession").then(s=>s.referenceSession?.state==="ready")'),'explicit upload confirmation');
  check(await evaluate(chat,'sent.length===0'),'Confirming uploads still does not send a prompt');
 }

 check(await evaluate(popup,'document.getElementById("nextStep").textContent.includes("Start generating")'),'Next-step instructions visible');
 const screenshot=async name=>{await evaluate(popup,'scrollTo(0,0);document.body.scrollTop=0;document.documentElement.scrollTop=0;document.getAnimations().forEach(a=>{try{a.finish()}catch{}})');await pause(400);const {data}=await call('Page.captureScreenshot',{format:'png',captureBeyondViewport:false},popup);fs.writeFileSync(path.join(out,name),Buffer.from(data,'base64'));};
 await screenshot('smart-flow-ready.png');
 await evaluate(popup,'document.getElementById("autoDownload").click()');
 await evaluate(popup,'document.getElementById("start").click()');
 await until(()=>evaluate(chat,'window.sent.length===1'),'first actual content-script send');
 check(await evaluate(chat,referenceRun?'sent[0].includes("STYLE LOCK: 3D ANIME ONLY")&&sent[0].includes("Frame: Frame 032")&&sent[0].includes("CHARACTER REFERENCE GUIDE")':['sent[0].includes("STYLE LOCK: 3D ANIME ONLY")','sent[0].includes("looking INTO the hall")','sent[0].includes("Frame: Frame 001")'].join('&&')),'Exact user workbook and required first frame reach Send');
 if(referenceRun)check(await evaluate(chat,'["Anaya","Arjun","Mehak","Trisha","Veer"].every(name=>sent[0].includes(name))'),'First frame includes named character reference guide');
 await until(()=>evaluate(popup,'chrome.storage.local.get("index").then(s=>s.index===1)'),'real file download and progress');
 await evaluate(popup,'chrome.tabs.sendMessage('+JSON.stringify((await evaluate(popup,'chrome.tabs.query({url:"https://chatgpt.com/*"}).then(t=>t[0].id)')))+',{action:"PAUSE"})');
 await evaluate(popup,'refresh()');
 check(await evaluate(chat,'sent.length===1'),'One storyboard frame completes before controlled Pause');
 if(referenceRun){
  check(await evaluate(popup,'chrome.storage.local.get("referenceSession").then(s=>s.referenceSession.state==="sent")'),'Observed submission consumes reference attachment step once');
  await evaluate(chat,'history.pushState({},"","/c/different-conversation")');
  const changed=await evaluate(popup,'chrome.tabs.query({url:"https://chatgpt.com/*"}).then(async t=>chrome.tabs.sendMessage(t[0].id,{action:"START",tabId:t[0].id}))');
  check(!changed.ok&&changed.error.includes('Attach the saved character references'),'New conversation cannot inherit reference confirmation');
  check(await evaluate(chat,'sent.length===1'),'Conversation change sends no image prompt');
  await evaluate(chat,'history.pushState({},"","/c/smart-flow-local-audit")');
 }
 const downloadRecords=await evaluate(popup,'chrome.downloads.search({limit:10,orderBy:["-startTime"]})');fs.writeFileSync(path.join(out,'download-records.json'),JSON.stringify(downloadRecords,null,2));
 const files=fs.readdirSync(out,{recursive:true}).filter(n=>n.endsWith('.png')&&n.includes(referenceRun?'Frame_032':'Frame_001'));check(files.length>0,'Actual Chrome download exists on disk: '+JSON.stringify(downloadRecords));
 check(files.every(f=>fs.statSync(path.join(out,f)).size>0),'Downloaded output is nonempty');
 await evaluate(popup,'window.confirm=()=>true;document.getElementById("repeatLine").value="Next";document.getElementById("repeatCount").value="2";document.getElementById("prepareRepeat").click()');
 await until(()=>evaluate(popup,'chrome.storage.local.get(["queueMode","phase"]).then(s=>s.queueMode==="repeat"&&s.phase==="idle")'),'prepare actual repeat run');
 await evaluate(popup,'document.getElementById("start").click()');
 await until(()=>evaluate(popup,'chrome.storage.local.get("phase").then(s=>s.phase==="done")'),'two actual repeat download cycles',35000);
 const sends=await evaluate(chat,'sent');check(sends.length===3&&sends[1]==='Next'&&sends[2]==='Next','Two repeats send exact Next after image saves');
 const history=await evaluate(popup,'chrome.storage.local.get(["index","frameHistory","pending"])');check(history.index===2&&history.pending===null&&history.frameHistory.length===2,'Repeat run completes with saved history and no pending work');
 await evaluate(popup,'refresh()');await screenshot('smart-flow-complete.png');
 const overflows=await evaluate(popup,'[...document.querySelectorAll(".repeat-mode,.extras,.history,.advanced")].forEach(e=>e.open=true);({body:document.body.scrollWidth,app:document.querySelector(".app").scrollWidth,ids:[...document.querySelectorAll("[id]")].map(e=>e.id)})');
 check(overflows.body<=370&&overflows.app<=370,'Expanded sections fit 370-pixel popup width');check(new Set(overflows.ids).size===overflows.ids.length,'No duplicate control IDs');
 await screenshot('smart-flow-expanded.png');
 const report={status:'PASS',checks,actualUserWorkbook:workbook,realChromeDownloads:true,actualExtensionStorage:true,syntheticChatGPTOnly:true,liveImageCreditsUsed:0,referenceRun,files:fs.readdirSync(out).filter(n=>n.endsWith('.png'))};
 fs.writeFileSync(path.join(out,'installed-extension-results.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
 }
 await call('Browser.close');
}finally{
 socket?.close();if(chrome.exitCode===null){await new Promise(r=>{const t=setTimeout(()=>{chrome.kill();r();},3000);chrome.once('exit',()=>{clearTimeout(t);r();});});}
 if(!path.resolve(profile).startsWith(path.resolve(os.tmpdir())+path.sep+'smart-flow-installed-'))throw Error('Unexpected test profile path');
 fs.rmSync(profile,{recursive:true,force:true,maxRetries:5,retryDelay:100});
}

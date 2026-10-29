// Actual unpacked extension, Chrome storage and downloads. ChatGPT document is
// fulfilled locally so generated prompts never reach the real ChatGPT service.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
const referenceRun=process.argv.includes('--references');
const root=fileURLToPath(new URL('../',import.meta.url));
const out=path.resolve(root,referenceRun?'../../Smart-Flow-References-Audit-20261029':'../../Smart-Flow-Audit-20261029');fs.mkdirSync(out,{recursive:true});
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
 window.sent=[];window.outputs=0;window.uploads=[];document.getElementById('chat-files').addEventListener('change',e=>{uploads.push([...e.target.files].map(f=>({name:f.name,size:f.size,type:f.type})));document.getElementById('attachments').textContent=uploads.at(-1).map(f=>f.name).join(' | ');});document.querySelector('form').addEventListener('submit',e=>{e.preventDefault();const editor=document.querySelector('textarea'),text=editor.value;if(!text)return;sent.push(text);const user=document.createElement('div');user.dataset.messageAuthorRole='user';user.dataset.messageId='user-'+sent.length;user.textContent=text;document.querySelector('#conversation').append(user);editor.value='';document.querySelector('#generation').innerHTML='<button aria-label="Stop generating">Stop</button>';setTimeout(()=>{document.querySelector('#generation').replaceChildren();outputs++;const a=document.createElement('div');a.dataset.messageAuthorRole='assistant';a.dataset.messageId='assistant-'+outputs;const b=document.createElement('button');b.type='button';b.dataset.testid='generated-image-preview';b.setAttribute('aria-label','Generated image '+outputs);const img=document.createElement('img');img.src=${JSON.stringify(pixel)}+'#output-'+outputs;b.append(img);a.append(b);document.querySelector('#conversation').append(a);},1200);});</script></body></html>`;
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
 await call('Browser.close');
}finally{
 socket?.close();if(chrome.exitCode===null){await new Promise(r=>{const t=setTimeout(()=>{chrome.kill();r();},3000);chrome.once('exit',()=>{clearTimeout(t);r();});});}
 if(!path.resolve(profile).startsWith(path.resolve(os.tmpdir())+path.sep+'smart-flow-installed-'))throw Error('Unexpected test profile path');
 fs.rmSync(profile,{recursive:true,force:true,maxRetries:5,retryDelay:100});
}

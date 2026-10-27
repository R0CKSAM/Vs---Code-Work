import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {spawn} from 'node:child_process';
const [url,chrome,screenshot]=process.argv.slice(2);
const profile=fs.mkdtempSync(path.join(os.tmpdir(),'smart-export-cdp-'));
const processChrome=spawn(chrome,['--headless','--disable-gpu','--disable-extensions','--no-first-run','--no-default-browser-check','--window-size=1280,900','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{stdio:'ignore'});
let socket;
try{
 const portFile=path.join(profile,'DevToolsActivePort');
 const start=Date.now();
 while(!fs.existsSync(portFile)){if(Date.now()-start>10000)throw new Error('Chrome did not start');await new Promise(r=>setTimeout(r,50));}
 const [port,endpoint]=fs.readFileSync(portFile,'utf8').trim().split('\n');
 socket=new WebSocket(`ws://127.0.0.1:${port}${endpoint.trim()}`);
 await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
 let next=0;const pending=new Map(),events=[];
 socket.onmessage=event=>{const data=JSON.parse(event.data);if(data.id){const callbacks=pending.get(data.id);pending.delete(data.id);if(data.error)callbacks.reject(new Error(JSON.stringify(data.error)));else callbacks.resolve(data.result);}else for(const handler of events)handler(data);};
 const call=(method,params={},sessionId)=>new Promise((resolve,reject)=>{const id=++next;pending.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params,sessionId}));});
 const {targetId}=await call('Target.createTarget',{url:'about:blank'});
 const {sessionId}=await call('Target.attachToTarget',{targetId,flatten:true});
 await call('Page.enable',{},sessionId);
 await call('Runtime.enable',{},sessionId);
 const loaded=new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('Page did not load')),15000);events.push(event=>{if(event.sessionId===sessionId&&event.method==='Page.loadEventFired'){clearTimeout(timer);resolve();}});});
 await call('Page.navigate',{url},sessionId);await loaded;
 const result=await call('Runtime.evaluate',{expression:`new Promise((resolve,reject)=>{const started=Date.now();const timer=setInterval(()=>{const text=document.getElementById('ui-test-result')?.textContent;if(text&&text!=='PENDING'){clearInterval(timer);resolve(text);}else if(Date.now()-started>15000){clearInterval(timer);reject(new Error('Storage checks timed out'));}},25);})`,awaitPromise:true,returnByValue:true},sessionId);
 if(result.exceptionDetails)throw new Error(JSON.stringify(result.exceptionDetails));
 const payload=JSON.parse(result.result.value);console.log(JSON.stringify(payload));
 if(payload.status!=='PASS')throw new Error(payload.error||'Storage checks failed');
 if(screenshot){const {data}=await call('Page.captureScreenshot',{format:'png',captureBeyondViewport:false},sessionId);fs.writeFileSync(screenshot,Buffer.from(data,'base64'));}
 await call('Browser.close');
}finally{
 socket?.close();
 if(processChrome.exitCode===null){await new Promise(resolve=>{const timer=setTimeout(()=>{processChrome.kill();resolve();},3000);processChrome.once('exit',()=>{clearTimeout(timer);resolve();});});}
 const resolved=path.resolve(profile),base=path.resolve(os.tmpdir())+path.sep+'smart-export-cdp-';
 if(!resolved.startsWith(base))throw new Error('Unexpected temporary profile path');
 fs.rmSync(resolved,{recursive:true,force:true,maxRetries:5,retryDelay:100});
}

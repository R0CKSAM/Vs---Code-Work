const fs=require('fs'),os=require('os'),path=require('path'),assert=require('assert'),{spawn}=require('child_process');
const profile=fs.mkdtempSync(path.join(os.tmpdir(),'indu-check-'));
const proc=spawn('C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',['--headless=new','--disable-gpu','--no-first-run','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{stdio:'ignore',windowsHide:true});
const sleep=ms=>new Promise(r=>setTimeout(r,ms));let socket,id=0,pending=new Map();
(async()=>{
 let port;for(let i=0;i<100;i++){try{port=fs.readFileSync(path.join(profile,'DevToolsActivePort'),'utf8').split('\n')[0];break}catch{}await sleep(100)}
 const targets=await(await fetch(`http://127.0.0.1:${port}/json`)).json();socket=new WebSocket(targets.find(x=>x.type==='page').webSocketDebuggerUrl);
 await new Promise((r,j)=>{socket.onopen=r;socket.onerror=j});socket.onmessage=e=>{const m=JSON.parse(e.data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(m.error):p.resolve(m.result)}};
 const call=(method,params={})=>new Promise((resolve,reject)=>{const n=++id;pending.set(n,{resolve,reject});socket.send(JSON.stringify({id:n,method,params}))});
 const evaluate=async expression=>{const r=await call('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.text);return r.result.value};
 const code=fs.readFileSync(path.join(__dirname,'../page.js'),'utf8');
 let checks=0;
 for(const [file,prefix,fn,title] of [[path.join(__dirname,'fixtures/ht.html'),'hindustanTimes','downloadHinduStanTimesPDF','Hindustan Times'],[path.join(__dirname,'fixtures/toi.html'),'TOI','downloadTOIV3PDF','Times of India']]){
  let html=fs.readFileSync(file,'utf8');const start=html.indexOf('<div class="form-container"');html=html.slice(start,html.indexOf('<p class="card-footer"',start));
  await evaluate(`document.body.innerHTML=${JSON.stringify(html)};window.${fn}=async()=>{window.sent={date:document.getElementById('${prefix}Date').value,city:document.getElementById('${prefix}City').value,sub:document.getElementById('${prefix}SubCity')?.value};};document.getElementById('${prefix}City').innerHTML='<option value="delhi">Delhi</option><option value="mumbai">Mumbai</option>';document.getElementById('${prefix}Date').value='2026-11-12';`);
  if(prefix!=='TOI')await evaluate(`const city=document.getElementById('${prefix}City'),sub=document.getElementById('${prefix}SubCity');city.onchange=()=>{sub.innerHTML='<option value="'+city.value+'-main">Main edition</option><option value="'+city.value+'-city">City edition</option>'};city.onchange();`);
  await evaluate(code);let info=await evaluate(`induPage('inspect')`);assert(info.ok);assert.equal(info.paper.title,title);checks+=2;
  let changed=await evaluate(`induPage('select',{id:'${prefix}City',value:'mumbai'})`);assert(changed.ok);assert.equal(changed.paper.fields[0].value,'mumbai');checks+=2;
  const selections=changed.paper.fields.map(f=>({id:f.id,value:f.value}));
  const result=await evaluate(`induPage('download',${JSON.stringify({paper:changed.paper,selections,date:'2026-10-15'})})`);assert(result.ok);const sent=await evaluate('window.sent');assert.equal(sent.date,'2026-10-15');assert.equal(sent.city,'mumbai');checks+=3;
  if(prefix!=='TOI'){assert.equal(sent.sub,'mumbai-main');checks++;}
  await evaluate('window.jspdf={jsPDF:class {text(){} save(){}}};');
  await evaluate(`window.originalPDF=window.jspdf.jsPDF;window.${fn}=async()=>{const doc=new window.jspdf.jsPDF();doc.text('Newspaper test',10,10);doc.save('test-2026-10-17.pdf')}`);
  const savedResult=await evaluate(`induPage('download',${JSON.stringify({paper:changed.paper,selections,date:'2026-10-17',attemptId:'actual-jspdf-test'})})`);
  assert(savedResult.ok&&savedResult.downloadRequested);assert(await evaluate('window.jspdf.jsPDF===window.originalPDF'));const savedStatus=await evaluate(`induPage('status')`);assert(savedStatus.task.id==='actual-jspdf-test'&&savedStatus.task.state==='complete');checks+=3;
  await evaluate('window.__induBatchBusy=true');assert(!(await evaluate(`induPage('download',${JSON.stringify({paper:changed.paper,selections,date:'2026-10-16'})})`)).ok);await evaluate('window.__induBatchBusy=false');checks++;
  await evaluate(`window.fetch=async()=>({ok:false,status:0,type:'opaque'});window.${fn}=async()=>{await fetch('https://ads.example/track')}`);
  assert((await evaluate(`induPage('download',${JSON.stringify({paper:changed.paper,selections,date:'2026-10-16'})})`)).ok);checks++;
  await evaluate(`window.fetch=async()=>({ok:false,status:400,type:'cors'});window.${fn}=async()=>{await fetch('https://d3i9pcxc8oepjn.cloudfront.net/hindustantimes/v2/download')}`);
  const apiFailure=await evaluate(`induPage('download',${JSON.stringify({paper:changed.paper,selections,date:'2026-10-16'})})`);assert(!apiFailure.ok&&apiFailure.error.includes('HTTP 400'));checks++;
  await evaluate(`window.${fn}=async()=>{alert('Edition missing')}`);const failed=await evaluate(`induPage('download',${JSON.stringify({paper:changed.paper,selections,date:'2026-10-16'})})`);assert(!failed.ok&&failed.error.includes('Edition missing'));assert.equal(await evaluate('window.__induBatchBusy'),false);checks+=2;
 }
 const popupHTML=fs.readFileSync(path.join(__dirname,'../popup.html'),'utf8').replace(/<script[\s\S]*?<\/script>/gi,'');
 const popupJS=fs.readFileSync(path.join(__dirname,'../popup.js'),'utf8');
 for(const version of ['1.2.0','1.1.1']){
  const result=await evaluate(`(async()=>{const f=document.createElement('iframe');document.body.append(f);const w=f.contentWindow;w.document.open();w.document.write(${JSON.stringify(popupHTML)});w.document.close();const fakeJob={phase:'retrying',dates:['2026-10-01','2026-10-02'],index:1,retryCount:2,nextAt:Date.now()+15000,history:[{date:'2026-10-01',status:'saved'}],paper:{path:'/test'},edition:'Delhi',error:'Temporary network error'};const mock={runtime:{getManifest:()=>({version:${JSON.stringify(version)}}),sendMessage:async m=>{w.sent=m;return {ok:true}}},storage:{local:{get:async()=>({job:fakeJob})},onChanged:{addListener:()=>{}}},tabs:{query:async()=>[{id:5,url:'https://www.indupaper.com/times-of-india.html'}]},scripting:{executeScript:async o=>[{result:await window.induPage(...o.args)}]}};Object.defineProperty(w,'chrome',{value:mock,configurable:true});w.confirm=()=>true;w.eval(${JSON.stringify(popupJS)});await new Promise(r=>setTimeout(r,100));const out={connection:w.document.getElementById('connection').textContent,status:w.document.getElementById('status').textContent,startDisabled:w.document.getElementById('startBatch').disabled,skipDisabled:w.document.getElementById('skip').disabled,detail:w.document.getElementById('detail').textContent};if(!out.skipDisabled){w.document.getElementById('skip').click();await new Promise(r=>setTimeout(r,50));out.action=w.sent?.action;}f.remove();return out;})()`);
  if(version==='1.2.0'){assert(result.status.includes('Automatic retry 2/3'));assert(result.startDisabled);assert(!result.skipDisabled&&result.action==='skip');assert(result.detail.includes('1 saved'));checks+=4;}
  else{assert(result.connection.includes('Update pending'));assert(result.startDisabled&&result.skipDisabled);checks+=2;}
 }
 console.log('PASS:',checks,'real-browser checks using live HT/TOI form markup: detection, city/sub-city dependency, date/edition selection, busy guard, failure handling.');
})().catch(e=>{console.error(e);process.exitCode=1}).finally(()=>{socket?.close();proc.kill()});

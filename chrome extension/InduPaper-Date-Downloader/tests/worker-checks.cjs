const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(path.join(__dirname,'../worker.js'),'utf8');
let checks=0;const check=(value,label)=>{assert(value,label);checks++;};
function harness(){
 let now=Date.parse('2026-11-12T10:00:00Z'),data={},items=[],calls=0,created=0,resumed=0,reports=[],awake=false;
 let tabs=[{id:5,url:'https://www.indupaper.com/hindustan-times.html',status:'complete'}];
 const listeners={},alarms=new Map();
 const paper={path:'/hindustan-times.html',slug:'hindustan-times',title:'Hindustan Times',dateId:'hindustanTimesDate',functionName:'downloadHinduStanTimesPDF',fields:[{id:'city',label:'City',options:[{value:'Delhi',text:'Delhi'}]},{id:'edition',label:'Sub City',options:[{value:'delhi',text:'Delhi'}]}]};
 let status={ok:true,ready:true,busy:false,task:null},answer={ok:true,downloadRequested:true},onDownload;
 const event=name=>({addListener:fn=>listeners[name]=fn});
 class Clock extends Date{constructor(...a){super(...(a.length?a:[now]));}static now(){return now;}}
 const chrome={
  power:{requestKeepAwake:level=>{assert.equal(level,'system');awake=true;},releaseKeepAwake:()=>{awake=false;}},
  storage:{local:{get:async()=>structuredClone(data),set:async x=>{data=structuredClone({...data,...x});},remove:async key=>{delete data[key];}}},
  alarms:{get:async n=>alarms.get(n),create:async(n,o)=>alarms.set(n,o),onAlarm:event('alarm')},
  runtime:{id:'test',onMessage:event('message'),onStartup:event('startup'),onInstalled:event('installed')},
  tabs:{get:async id=>{const t=tabs.find(t=>t.id===id);if(!t)throw Error('Tab not found');return t;},query:async()=>tabs,create:async o=>{const t={id:100+created++,url:o.url,status:'complete'};tabs.push(t);return t;}},
  downloads:{onDeterminingFilename:event('filename'),onChanged:event('changed'),download:async o=>{reports.push(o);return 900+reports.length;},search:async o=>structuredClone(items.filter(d=>o.id!=null?d.id===o.id:!o.startedAfter||Date.parse(d.startTime)>=Date.parse(o.startedAfter))),resume:async id=>{resumed++;items.find(d=>d.id===id).state='in_progress';}},
  scripting:{executeScript:async o=>{
   if(o.args[0]==='inspect')return [{result:{ok:true,paper}}];
   if(o.args[0]==='status')return [{result:status}];
   calls++;if(onDownload)await onDownload(o);return [{result:answer}];
  }}
 };
 const context=vm.createContext({chrome,Date:Clock,URL,console,crypto:require('node:crypto').webcrypto,importScripts:()=>{},induPage:()=>{}});
 vm.runInContext(source+'\n globalThis.api={get,edit,datesBetween,step,finish,bindDownload,nameDownload,reconcile};',context);
 const cmd=m=>new Promise(resolve=>listeners.message(m,{},resolve));
 const start=(options={})=>cmd({action:'start',tabId:5,start:'2026-09-01',end:'2026-09-03',selections:[{id:'city',value:'Delhi'},{id:'edition',value:'delhi'}],...options});
 return {api:context.api,chrome,listeners,cmd,start,paper,alarms,
  get job(){return data.job;},set job(v){data.job=structuredClone(v);},get calls(){return calls;},get created(){return created;},get resumed(){return resumed;},get reports(){return reports;},get awake(){return awake;},
  set answer(v){answer=v;},set status(v){status=v;},set onDownload(v){onDownload=v;},set tabs(v){tabs=v;},set items(v){items=v;},get items(){return items;},advance:ms=>now+=ms,
  item(id,state='complete'){return {id,state,exists:true,filename:'C:/Downloads/hindustan-times-2026-09-01.pdf',referrer:'https://www.indupaper.com/hindustan-times.html',startTime:new Date(now).toISOString()};}
 };
}
(async()=>{
 let h=harness();check(h.api.datesBetween('2028-02-28','2028-03-01').length===3,'leap date range');assert.throws(()=>h.api.datesBetween('2026-02-30','2026-03-01'));checks++;
 const starts=await Promise.all([h.start(),h.start()]);check(starts.filter(x=>x.ok).length===1,'double Start creates one batch');
 await h.api.step();check(h.job.phase==='waiting'&&!!h.job.attemptId,'attempt persisted before site call');
 let suggested;await h.api.bindDownload({...h.item(1),referrer:'https://www.indupaper.com/times-of-india.html'},x=>suggested=x);check(!suggested,'other newspaper download ignored');
 h.items=[h.item(2,'in_progress')];await h.api.bindDownload(h.items[0],x=>suggested=x);check(suggested.conflictAction==='uniquify'&&suggested.filename.includes('hindustan-times/delhi-delhi/'),'edition folder and no overwrite');
 await h.cmd({action:'pause'});h.items[0].state='complete';await Promise.all([h.api.finish(2),h.api.finish(2)]);check(h.job.index===1&&h.job.phase==='paused','concurrent completion advances once and honors pause');
 await h.cmd({action:'skip'});check(h.job.index===2&&h.job.phase==='queued','Skip automatically schedules next date');check(h.alarms.has('next'),'Skip has alarm');
 h=harness();await h.start();await h.cmd({action:'pause'});h.tabs=[];await h.listeners.startup();check(h.job.phase==='paused'&&h.created===0,'startup preserves manual pause');
 h=harness();await h.start();h.answer={ok:false,error:'Newspaper server returned HTTP 503',transient:true,downloadRequested:false};
 for(const [i,delay] of [15000,45000,120000].entries()){await h.api.step();check(h.job.phase==='retrying'&&h.job.retryCount===i+1,'bounded retry '+(i+1));const before=h.calls;await h.api.step();check(h.calls===before,'backoff honored');h.advance(delay+1);}
 await h.api.step();check(h.job.phase==='queued'&&h.job.index===1&&h.job.history[0].status==='failed'&&h.calls===4,'three retries then automatically continue');
 h=harness();await h.start();h.answer={ok:false,error:'Newspaper server returned HTTP 404',transient:false};await h.api.step();check(h.job.phase==='queued'&&h.job.index===1&&!h.job.retryCount,'missing date recorded without a retry loop');
 h=harness();await h.start();await h.api.step();const saved=h.item(8);h.items=[saved];h.tabs=[];await h.listeners.startup();check(h.job.index===1&&h.calls===1,'restart adopts saved PDF without resubmission');
 h=harness();await h.start();h.tabs=[];await h.listeners.startup();await h.api.step();check(h.created===1&&h.job.phase==='waiting','queued restart restores newspaper tab');
 h=harness();await h.start();await h.api.step();h.tabs=[];await h.listeners.startup();check(h.created===1&&h.job.phase==='retrying','unfinished restart with no download safely retries');
 h=harness();await h.start();await h.api.step();const inProgress=h.item(9,'in_progress');h.items=[inProgress];await h.listeners.startup();check(h.job.phase==='downloading'&&h.calls===1,'restart monitors existing download');
 await h.cmd({action:'pause'});inProgress.state='complete';h.items=[inProgress];await h.api.finish(9);check(h.job.index===1&&h.job.phase==='paused','pause during recovery respected');
 h=harness();await h.start();await h.api.step();h.status={ok:true,ready:true,busy:true,task:{id:h.job.attemptId,state:'working'}};await h.api.reconcile();check(h.job.phase==='waiting'&&h.calls===1,'active generation not resubmitted');
 h.status={ok:true,ready:true,busy:false,task:{id:h.job.attemptId,state:'complete',downloadRequested:true}};h.advance(61000);await h.api.reconcile();check(h.job.phase==='paused'&&h.job.pauseReason==='uncertain','uncertain PDF request pauses rather than duplicating');
 h=harness();await h.start();await h.api.step();const network={...h.item(10,'interrupted'),error:'NETWORK_FAILED',canResume:true};h.items=[network];await h.api.reconcile();check(h.resumed===1&&h.job.phase==='downloading'&&h.calls===1,'resume interrupted transfer without regenerating');
 h=harness();await h.start();await h.api.step();h.items=[{...h.item(11,'interrupted'),error:'USER_CANCELED'}];await h.api.reconcile();check(h.job.phase==='paused'&&h.calls===1,'user cancellation does not auto retry');
 h=harness();await h.start();h.onDownload=async()=>{h.items=[h.item(12,'in_progress')];await h.api.bindDownload(h.items[0],()=>{});};h.answer={ok:false,error:'late error',transient:true};await h.api.step();check(h.job.phase==='downloading','late site error does not override transfer');
 h=harness();await h.start();h.onDownload=async()=>{const j=h.job;j.phase='paused';j.pauseReason='user';h.job=j;};await h.api.step();check(h.job.phase==='paused','late callback cannot undo pause');
 h=harness();await h.start();h.tabs=[{id:5,url:'https://example.com',status:'complete'}];await h.api.step();check(h.job.phase==='paused'&&h.calls===0,'navigation protection');
 h=harness();await h.start();await h.api.step();h.items=[{...h.item(20,'in_progress'),bytesReceived:100}];await h.api.reconcile();h.advance(600001);await h.api.reconcile();check(h.job.phase==='paused'&&h.calls===1,'stalled transfer pauses without generating another PDF');
 h=harness();await h.start();await h.api.step();h.items=[{...h.item(21,'interrupted'),error:'NETWORK_FAILED',canResume:false}];h.tabs=[];await h.listeners.startup();h.items=[];h.advance(15001);await h.api.step();check(h.created===1&&h.job.phase==='waiting','restart after interrupted transfer restores missing tab');
 h=harness();await h.start({continueOnError:false});h.answer={ok:false,error:'HTTP 404',httpStatus:404};await h.api.step();check(h.job.phase==='paused'&&h.job.index===0,'strict mode remains available');
 h=harness();await h.start();h.answer={ok:false,error:'HTTP 403',httpStatus:403};await h.api.step();check(h.job.phase==='paused'&&h.job.index===0,'access errors require review rather than bypass');
 h=harness();await h.start();h.answer={ok:false,error:'HTTP 404',httpStatus:404};for(let i=0;i<3;i++)await h.api.step();check(h.job.phase==='done'&&h.job.history.length===3,'all unavailable dates terminate instead of leaving a stuck queue');check(h.job.history.every(x=>x.status==='failed'),'unavailable dates never marked saved');check(h.reports.length===1&&decodeURIComponent(h.reports[0].url).includes('failed'),'completion automatically saves honest CSV report');
 await h.cmd({action:'retryMissed'});check(h.job.phase==='queued'&&h.job.dates.length===3&&h.job.history.length===0,'retry missed creates a focused new batch');
 h=harness();await h.start();let old=h.job;old.phase='paused';old.pauseReason='error';old.error='HTTP 500 Automatic retries exhausted.';old.retryCount=3;h.job=old;await h.listeners.installed();check(h.job.index===1&&h.job.phase==='queued'&&h.job.history[0].status==='failed','update repairs an old exhausted-server-error pause');
 h=harness();await h.start();old=h.job;old.phase='done';old.index=3;old.history=[{date:'2026-09-01',status:'saved'},{date:'2026-09-02',status:'failed'},{date:'2026-09-03',status:'skipped'}];h.job=old;await h.cmd({action:'retryMissed'});check(h.job.dates.join(',')==='2026-09-02,2026-09-03','retry missed excludes successful dates');
 h=harness();await h.start({start:'2025-12-01',end:'2025-12-31'});h.answer={ok:false,error:'HTTP 500',httpStatus:500,transient:true};for(let day=0;day<31;day++){for(const delay of [15001,45001,120001]){await h.api.step();check(h.job.phase==='retrying','server failure remains unattended during retry');h.advance(delay);}await h.api.step();}check(h.job.phase==='done'&&h.job.history.length===31&&h.reports.length===1,'entire 31-day failing batch finishes with one report');check(h.job.history.every(x=>x.status==='failed'&&x.attempts===4),'every failed date honestly records four attempts');
 h=harness();await h.start();h.answer={ok:false,error:'HTTP 404',httpStatus:404};await h.api.step();await h.cmd({action:'report'});check(h.reports[0].filename.includes('_PARTIAL'),'interim report clearly labeled');await h.api.step();await h.api.step();check(h.reports.length===2&&!h.reports[1].filename.includes('_PARTIAL'),'interim report does not suppress final report');
 h=harness();await h.start();old=h.job;old.phase='paused';old.pauseReason='user';old.error='HTTP 500';old.retryCount=3;h.job=old;await h.listeners.installed();check(h.job.phase==='paused'&&h.job.index===0,'update does not override manual pause');
 h=harness();await h.start();check(h.awake,'active batch prevents idle sleep');await h.cmd({action:'pause'});check(!h.awake,'manual pause releases keep-awake');await h.cmd({action:'resume'});check(h.awake,'resume restores keep-awake');h.answer={ok:false,error:'HTTP 404',httpStatus:404};for(let i=0;i<3;i++)await h.api.step();check(!h.awake,'completion releases keep-awake');
 const latest=h.reports.at(-1);let reportName;await h.api.nameDownload({url:latest.url,byExtensionId:'test'},value=>reportName=value);check(reportName.filename===latest.filename&&reportName.conflictAction==='uniquify','CSV reports keep their explicit folder and filename');
 console.log(`PASS: ${checks} downloader checks (retry limits, skip, restart recovery, duplicate protection, cancellation and pause races).`);
})().catch(e=>{console.error(e);process.exitCode=1;});

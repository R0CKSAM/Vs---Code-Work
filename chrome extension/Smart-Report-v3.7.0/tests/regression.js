'use strict';
// Run from a localhost HTTP server. No corporate service is contacted.
(async () => {
  const results = [], sources = {};
  const assert = (condition, message) => { if (!condition) throw Error(message); };
  async function test(name, fn) {
    try { await fn(); results.push('PASS ' + name); }
    catch (e) { results.push('FAIL ' + name + ': ' + e.message); }
  }
  async function rejects(fn, pattern) {
    try { await fn(); } catch (e) { assert(pattern.test(e.message), e.message); return; }
    throw Error('Expected rejection');
  }
  for (const file of ['background.js','capture-engine.js','capture-page.js','popup.js','preview.js','company-config.js']) {
    const response = await fetch('../' + file);
    assert(response.ok, 'Missing source: ' + file);
    sources[file] = await response.text();
    await test(file + ' syntax', () => new Function(sources[file]));
  }

  async function engine({end, maxScroll, rootTop=0, bottom=1000, blank=false, startError=false}) {
    let clock=0, top=0, captures=0, restored=false, detached=false;
    const state=()=>({href:'fixture',width:1600,height:1000,rootTop,visibleTop:rootTop,bottom,
      scrollTop:top,maxScroll,contentEnd:end,scrollWidth:1600,clientWidth:1600,collapsed:[],errors:[],
      missing:blank?['blank chart']:[],visiblePanels:1,ready:'complete',busy:0,paintedCanvases:1,
      meaningful:1,noData:[],canvasRegions:[],expanded:0});
    const chrome={debugger:{attach:async()=>{},detach:async()=>{detached=true;},sendCommand:async(_,m)=>{
      if(m==='Page.captureScreenshot'){captures++;return {data:'x'};}
    }},scripting:{executeScript:async args=>{
      if(args.files)return [];
      const [op,arg]=args.args;
      if(op==='start'&&startError)throw Error('injected startup failure');
      if(op==='scroll')top=Math.min(maxScroll,arg.top);
      if(op==='restore')restored=true;
      return [{result:op==='expand'?{count:0}:state()}];
    }}};
    class Canvas {
      getContext(){return {drawImage(){}};}
      async convertToBlob(){return {size:1,type:'image/png',arrayBuffer:async()=>new Uint8Array([1]).buffer};}
    }
    const run=new Function('chrome','Date','sleep','progress','isDashboardTab','OffscreenCanvas',
      'createImageBitmap','Blob','atob','btoa','MAX_ATTACH_BYTES','log',
      sources['capture-engine.js']+'\nreturn captureDashboardTiles(1,{dashboard:"fixture"});');
    let shot, error;
    try { shot=await run(chrome,{now:()=>clock},async ms=>{clock+=ms;},async()=>{},()=>true,Canvas,
      async()=>({width:1600,height:1000,close(){}}),class{},()=>'',()=>'x',2621440,async()=>{}); }
    catch(e){error=e;}
    assert(restored&&detached,'Capture cleanup did not run');
    return {shot,error,captures};
  }
  for(const c of [
    {name:'single viewport without trailing scroll',end:1016,maxScroll:0,height:1000},
    {name:'multiple tiles without trailing scroll',end:1516,maxScroll:500,height:1500},
    {name:'nested scroller with toolbar and footer',end:1316,maxScroll:500,rootTop:100,bottom:900,height:1400},
    {name:'last one-pixel strip is retained',end:1001,maxScroll:100,height:1001}
  ]) await test(c.name,async()=>{const r=await engine(c);assert(!r.error,r.error?.message);assert(r.shot.meta.height===c.height,'Wrong output height');});
  await test('blank chart blocks capture and restores tab',async()=>{const r=await engine({end:1000,maxScroll:0,blank:true});assert(r.error&&r.captures===0,'Blank chart accepted');});
  await test('startup failure still restores tab',async()=>{const r=await engine({end:1000,maxScroll:0,startError:true});assert(r.error,'Expected startup failure');});

  // Real Chromium DOM and canvas checks, separate from the mocked CDP engine.
  async function panel(markup, extraStyle='') {
    const frame=document.createElement('iframe');frame.style.cssText='width:1600px;height:1000px;border:0';
    document.body.append(frame);
    const w=frame.contentWindow,d=w.document;
    d.open();d.write('<style>html,body{margin:0}.panel-container{width:800px;height:1000px}'+extraStyle+'</style>'+markup);d.close();
    w.eval(sources['capture-page.js']);
    try{return w.__SR_CAPTURE_PAGE__('start');}
    finally{try{w.__SR_CAPTURE_PAGE__('restore');}catch{}frame.remove();}
  }
  for(const value of ['42','UP','OK','Healthy','No data'])await test('real DOM panel value '+value,async()=>{
    const s=await panel('<div class="panel-container"><h2>Panel title</h2><div class="panel-content">'+value+'</div></div>');
    assert(!s.missing.length,s.missing.join(';'));assert(s.contentEnd<=1000,'End extends beyond reachable pixels');
  });
  for(const value of ['', 'Loading...', '<span hidden>42</span>', '<canvas width="300" height="200"></canvas>'])await test('real DOM rejects empty/loading panel '+value,async()=>{
    const s=await panel('<div class="panel-container"><h2>Title 123</h2><div class="panel-content">'+value+'</div></div>');
    assert(s.missing.length>0,'Empty/loading visualization accepted');
  });

  const dashboard='https://grafana-apj.trafficpeak.live/d/test/dashboard?from=now%2Fd&to=now&refresh=1m';
  async function worker(initial={}) {
    let listener, calls=0, tabs=0, failNetwork=false, onPost=async()=>{};
    const db={smartReportVersion:'3.7.1',mode:'stopped',config:{dashboard,to:'test@example.com',interval:15},...initial};
    const storage={get:async keys=>structuredClone(Object.fromEntries((Array.isArray(keys)?keys:[keys]).map(k=>[k,db[k]]))),
      set:async value=>Object.assign(db,structuredClone(value)),remove:async()=>{}};
    const chrome={storage:{local:storage,session:storage},identity:{getRedirectURL:()=>''},
      runtime:{id:'test',getURL:path=>'chrome-extension://test/'+path,onStartup:{addListener(){}},onInstalled:{addListener(){}},
        onMessage:{addListener(f){listener=f;}},getPlatformInfo:async()=>({})},
      tabs:{create:async()=>{tabs++;return {id:1};}},
      alarms:{clear:async()=>{},get:async()=>null,create:async()=>{},onAlarm:{addListener(){}}},notifications:{create:async()=>{}}};
    const load=new Function('chrome','importScripts','COMPANY_MICROSOFT','COMPANY_POLICY','setInterval','clearInterval','fetch',
      sources['background.js']+`\nreturn (async()=>{await restoreFlight;return {run,schedule,restoreAlarm,captureSignature,isDashboardTab,
        setAccess:f=>getAccess=f,setScreenshot:f=>screenshot=f};})();`);
    const api=await load(chrome,()=>{},
      {clientId:'00000000-0000-0000-0000-000000000001',tenantId:'00000000-0000-0000-0000-000000000002'},
      {allowedRecipientDomains:['example.com']},()=>1,()=>{},async url=>{
        assert(url.endsWith('/sendMail'),'Unexpected network request');calls++;
        if(failNetwork)throw Error('simulated offline');await onPost();return {status:202};
      });
    api.setAccess(async()=>'mock-token');
    api.setScreenshot(async()=>({meta:{width:1600,height:1000},data:'eA==',ext:'png',mime:'image/png'}));
    return {api,db,calls:()=>calls,tabs:()=>tabs,offline:()=>{failNetwork=true;},onPost:fn=>{onPost=fn;},
      approve:()=>{db.approvedCaptureSignature=api.captureSignature(db.config);},
      message:msg=>new Promise(resolve=>listener(msg,{id:'test',url:'chrome-extension://test/preview.html'},resolve))};
  }
  await test('stale preview rejected even with identical dashboard settings',async()=>{
    const w=await worker();w.db.capturePreview='image-B';w.db.capturePreviewSignature=w.api.captureSignature(w.db.config);w.db.capturePreviewId='B';
    const old=await w.message({action:'APPROVE_CAPTURE',previewId:'A'});assert(!old.ok,'Stale approval accepted');
    const current=await w.message({action:'APPROVE_CAPTURE',previewId:'B'});assert(current.ok,current.error);
  });
  await test('preview without identity cannot approve',async()=>{
    const w=await worker();w.db.capturePreview='image';w.db.capturePreviewSignature=w.api.captureSignature(w.db.config);
    const r=await w.message({action:'APPROVE_CAPTURE'});assert(!r.ok,'Legacy approval accepted');
  });
  await test('changed dashboard cannot approve old preview',async()=>{
    const w=await worker();w.db.capturePreview='image';w.db.capturePreviewSignature=w.api.captureSignature(w.db.config);w.db.capturePreviewId='A';
    w.db.config.dashboard+='&var-region=new';
    const r=await w.message({action:'APPROVE_CAPTURE',previewId:'A'});assert(!r.ok,'Changed settings approved');
  });
  for(const testSend of [false,true])await test('pause during token renewal cancels '+(testSend?'test':'scheduled')+' mail',async()=>{
    const w=await worker();w.approve();w.db.mode='running';
    w.api.setAccess(async()=>{await w.api.schedule('paused');return 'mock-token';});
    await rejects(()=>w.api.run(testSend,false),/cancelled/);
    assert(w.calls()===0,'Email submitted after pause');assert(!w.db.failedMail,'Cancellation counted as failure');
    assert(!w.db.submissionPending,'Cancelled run left uncertain submission');
  });
  await test('changed recipients during token renewal prevent stale submission',async()=>{
    const w=await worker();w.approve();w.api.setAccess(async()=>{w.db.config.to='changed@example.com';return 'mock-token';});
    await rejects(()=>w.api.run(true,false),/settings changed/);assert(w.calls()===0,'Stale recipients used');
  });
  await test('approved successful send increments acceptance exactly once',async()=>{
    const w=await worker();w.approve();await w.api.run(true,false);
    assert(w.calls()===1&&w.db.sent===1&&w.db.sentTest===1,'Wrong acceptance count');assert(!w.db.submissionPending,'Submission flag not cleared');
  });
  await test('unapproved email blocked before capture/submission',async()=>{
    const w=await worker();await rejects(()=>w.api.run(true,false),/Check screenshot/);assert(w.calls()===0,'Unapproved email submitted');
  });
  await test('preview opens without popup and leaves mail counters unchanged',async()=>{
    const w=await worker();await w.api.run(false,true);
    assert(w.tabs()===1&&w.db.capturePreviewId,'Preview not opened/stored');assert(!w.db.sent&&!w.db.failedMail&&w.calls()===0,'Preview affected mail');
  });
  await test('network uncertainty pauses even a manual test and survives restart',async()=>{
    const w=await worker();w.approve();w.db.mode='running';w.offline();
    await rejects(()=>w.api.run(true,false),/acceptance is unconfirmed/);
    assert(w.db.mode==='paused'&&w.db.submissionPending,'Uncertain send did not pause');
    const recovered=await worker({...w.db,mode:'running'});
    assert(recovered.db.mode==='paused'&&recovered.calls()===0,'Restart resumed uncertain submission');
  });
  await test('upgrade pauses old schedule and requires fresh approval',async()=>{
    const w=await worker({smartReportVersion:'3.7.0',mode:'running',approvedCaptureSignature:'old'});
    assert(w.db.smartReportVersion==='3.7.1'&&w.db.mode==='paused'&&!w.db.approvedCaptureSignature,'Unsafe upgrade');
  });
  await test('actual URL matching rejects changed filters',async()=>{
    const w=await worker();assert(w.api.isDashboardTab(dashboard,dashboard),'Matching URL rejected');
    assert(!w.api.isDashboardTab(dashboard+'&var-region=other',dashboard),'Changed filter accepted');
  });
  await test('pause after POST keeps the accepted outcome accurate',async()=>{
    const w=await worker();w.approve();w.db.mode='running';w.onPost(()=>w.api.schedule('paused'));
    await w.api.run(false,false);
    assert(w.calls()===1&&w.db.sent===1&&w.db.lastMailOutcome==='accepted'&&w.db.mode==='paused','Accepted mail misreported');
  });
  await test('capture failure never submits and releases busy lock for retry',async()=>{
    const w=await worker();w.approve();w.api.setScreenshot(async()=>{throw Error('blank chart');});
    await rejects(()=>w.api.run(true,false),/blank chart/);
    assert(w.calls()===0&&w.db.failedMail===1,'Wrong failed-capture outcome');
    w.api.setScreenshot(async()=>({meta:{},data:'x',ext:'png',mime:'image/png'}));
    await w.api.run(true,false);assert(w.calls()===1&&w.db.sent===1,'Busy lock stuck after failure');
  });
  await test('pause during capture prevents submission',async()=>{
    const w=await worker();w.approve();w.db.mode='running';
    w.api.setScreenshot(async()=>{await w.api.schedule('paused');return {meta:{}};});
    await rejects(()=>w.api.run(false,false),/cancelled/);assert(w.calls()===0,'Cancelled capture submitted');
  });
  await test('resume cannot revive an in-flight cancelled report',async()=>{
    const w=await worker();w.approve();w.db.mode='running';
    w.api.setAccess(async()=>{await w.api.schedule('paused');await rejects(()=>w.api.schedule('running'),/Wait/);return 'mock-token';});
    await rejects(()=>w.api.run(false,false),/cancelled/);assert(w.calls()===0,'Cancelled report revived');
  });
  document.getElementById('results').textContent=results.join('\n')+'\nTOTAL '+results.length+'; FAILED '+results.filter(x=>x.startsWith('FAIL')).length;
  document.title=results.some(x=>x.startsWith('FAIL'))?'FAIL':'PASS';
})().catch(e=>{document.getElementById('results').textContent='HARNESS ERROR: '+e.stack;document.title='FAIL';});

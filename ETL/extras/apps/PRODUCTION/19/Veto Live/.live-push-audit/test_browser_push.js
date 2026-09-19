async function runBrowserPushTests(source) {
  new Function(source);
  document.body.innerHTML = ['liveButton','takeLive','clearLive','programUnavailable','programState','programUpdated','liveStatus','programName','programDetails','stage','dimensions'].map(id=>`<div id="${id}"></div>`).join('')+'<img id="programImage"><img id="preview">';
  const slice=(start,end)=>source.slice(source.indexOf(start),source.indexOf(end));
  const functions=slice('function renderSnapshotKey(', 'function queueDisplayName(')+slice('function scheduleRender(', 'async function download(')+slice('function updateLiveButtons(', 'async function init(')+slice('async function liveCommand(', 'function outputStartReady(');
  const setup = `
    const $=id=>document.getElementById(id),clone=x=>JSON.parse(JSON.stringify(x));
    const clientId='test',boot={program_monitor:true,decklink_key_pairs:{output:'SDI 1'}};
    let cfg={title:'first'},template='t1',lastShown=null,shownRevision=null,latestSessions={can_manage:true};
    let latestLive={active:false},liveCommandBusy=false,liveRefreshBusy=false,liveStatusKnown=false,liveStatusEpoch=0;
    let programUrl=null,programFetchBusy=false,programRefreshAgain=false,programReady=false,displayedProgramRevision=null,displayedProgramDynamic=false;
    let renderTimer=null,renderToken=0,previewUrl='',previewReady=false,scheduledPreview='',readyPreviewSnapshot='',previewRenderBusy=false,previewRenderAgain=false;
    let presetSaving=false,uploadBusy=false,fetchHandler,decodeHandler=()=>Promise.resolve(),errors=[];
    const getConfig=()=>cfg;
    const request=()=>({client_id:clientId,template,config:cfg,update_live:false});
    const setError=value=>{if(value)errors.push(value)};
    const syncQueueSelection=()=>{},updateQueueControls=()=>{},syncProjectLock=()=>updateLiveButtons(),syncMediaPreview=()=>{},layoutTextBoxes=()=>{},renderCustomOverlay=async()=>{};
    const fetch=(...args)=>fetchHandler(...args);
    const Image=class{constructor(){this.naturalWidth=1920;this.naturalHeight=1080}decode(){return decodeHandler(this)}};
    async function apiJson(path,payload){const response=await fetch(path,{body:JSON.stringify(payload)});if(!response.ok)throw Error('Command failed');return response.json()}
    const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
    const defer=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return{promise,resolve,reject}};
    const status=revision=>({active:true,owned_by_requester:true,program_revision:revision,on_air:revision,clear_mode:'external-key',output:'output',preset:'HD 1080i50',program_dynamic:false});
    const frame=revision=>({ok:true,headers:new Headers({'X-Program-Revision':revision}),blob:async()=>new Blob(['frame'],{type:'image/png'})});
    const assert=(value,message)=>{if(!value)throw Error(message)};
    const tests=[];
  `;
  const cases = `
    applyLiveStatus(status('old'));previewReady=true;readyPreviewSnapshot=currentSnapshotKey();
    const slowMonitor=defer();let monitorRequests=0;
    fetchHandler=async path=>path==='/api/live/show'?{ok:true,json:async()=>status('new')}:(monitorRequests++,slowMonitor.promise);
    const command=liveCommand('/api/live/show',{});
    const immediate=await Promise.race([command.then(()=>true),new Promise(resolve=>setTimeout(()=>resolve(false),80))]);
    assert(immediate,'Push waited for monitor download');assert(!liveCommandBusy,'Push remained locked');assert(!$('takeLive').disabled,'Monitor blocked ready preview');
    slowMonitor.resolve(frame('new'));await tick();await tick();assert(displayedProgramRevision==='new','Monitor did not catch up');tests.push('push resolves while monitor is pending');

    const staleStatus=defer();
    fetchHandler=path=>path.startsWith('/api/live/status')?staleStatus.promise:path==='/api/live/show'?Promise.resolve({ok:true,json:async()=>status('newer')}):Promise.resolve(frame('newer'));
    const polling=refreshLive();await tick();await liveCommand('/api/live/show',{});staleStatus.resolve({ok:true,json:async()=>status('old')});await polling;await tick();
    assert(latestLive.program_revision==='newer','Old poll overwrote push revision');tests.push('pre-command status cannot replace command result');

    let downloads=0;fetchHandler=async()=>{downloads++;return frame('newer')};
    await refreshProgram();assert(downloads===0,'Unchanged still frame downloaded again');
    latestLive.program_dynamic=true;await refreshProgram();assert(downloads===1,'Video monitor stopped updating');
    latestLive.program_dynamic=false;await refreshProgram();assert(downloads===2,'Final video frame was not fetched');await refreshProgram();assert(downloads===2,'Final video frame downloaded repeatedly');tests.push('static monitor skips redundant downloads and captures final media frame');

    latestLive.program_dynamic=true;const finishingVideo=defer();fetchHandler=()=>finishingVideo.promise;const finishingFetch=refreshProgram();latestLive.program_dynamic=false;finishingVideo.resolve(frame('newer'));await finishingFetch;
    assert(displayedProgramDynamic,'Video completion during fetch lost final-frame refresh');downloads=0;fetchHandler=async()=>{downloads++;return frame('newer')};await refreshProgram();await refreshProgram();assert(downloads===1,'Final video frame was not refreshed exactly once after pending fetch');tests.push('video ending during monitor fetch still refreshes final frame');

    const previous=$('programImage').src,decode=defer();decodeHandler=()=>decode.promise;applyLiveStatus(status('decode-pending'));fetchHandler=async()=>frame('decode-pending');
    const decoding=refreshProgram();await tick();assert($('programImage').src===previous,'Visible image replaced before decode');assert($('programUnavailable').hidden,'Monitor blanked during replacement');
    applyLiveStatus(status('after-decode'));decode.resolve();await decoding;assert($('programImage').src===previous,'Stale decoded image replaced current frame');decodeHandler=()=>Promise.resolve();tests.push('program frame swaps only after decode and revision validation');

    fetchHandler=async()=>{throw Error('offline')};await refreshProgram();assert($('programImage').src===previous,'Monitor failure discarded last frame');assert(!$('takeLive').disabled,'Monitor failure blocked push');tests.push('monitor failures retain picture without blocking push');

    let active=0,maxActive=0;const pending=[],requested=[];
    fetchHandler=async(path,options)=>{assert(path==='/api/render','Unexpected preview request');active++;maxActive=Math.max(maxActive,active);requested.push(JSON.parse(options.body).config.title);const deferred=defer();pending.push(deferred);await deferred.promise;active--;return frame('preview')};
    cfg.title='first';scheduleRender(false);await tick();cfg.title='second';scheduleRender(false);await tick();cfg.title='third';scheduleRender(false);await tick();
    assert(requested.length===1,'Preview edits started concurrent renders');pending[0].resolve();await tick();await tick();assert(!previewReady,'Outdated preview became ready');assert(requested.join(',')==='first,third','Preview did not coalesce to newest edit');pending[1].resolve();await tick();await tick();
    assert(maxActive===1,'More than one preview request was active');assert(previewReady&&readyPreviewSnapshot===currentSnapshotKey(),'Latest preview snapshot did not become ready');tests.push('rapid edits render single-flight with latest snapshot only');

    cfg._web_text_role='title';cfg.text_styles={title:{}};updateLiveButtons();assert(!$('takeLive').disabled,'Selecting an unmodified text role blocked push');tests.push('editor-only selection does not invalidate preview');
    cfg.title='unrendered edit';updateLiveButtons();assert($('takeLive').disabled,'Unrendered config was allowed on air');tests.push('push requires the exact decoded preview snapshot');
    if(programUrl)URL.revokeObjectURL(programUrl);if(previewUrl)URL.revokeObjectURL(previewUrl);
    return tests;
  `;
  return new (Object.getPrototypeOf(async function(){}).constructor)(setup+functions+cases)();
}

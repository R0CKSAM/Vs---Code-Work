'use strict';
/* Fixed-width viewport tiles; never capture a giant off-screen compositor surface.
 * All image processing is local in this service worker. No offscreen document or
 * external screenshot service is used. */
async function captureDashboardTiles(tabId,c){
  const target={tabId}, width=1600,height=1000,deadline=Date.now()+240000;
  let attached=false, started=false, bitmaps=[];
  const cmd=(m,p={})=>chrome.debugger.sendCommand(target,m,p);
  async function page(op,arg={}){
    if(Date.now()>deadline&&op!=='restore')throw Error('Full dashboard capture exceeded 4 minutes. Reduce open sections or check slow panels, then retry.');
    const r=await chrome.scripting.executeScript({target:{tabId},func:(op,arg)=>globalThis.__SR_CAPTURE_PAGE__(op,arg),args:[op,arg]});
    if(!r[0]?.result)throw Error('Grafana did not return capture diagnostics. Open the dashboard and retry.');
    return r[0].result;
  }
  function validate(s){
    if(s.login)throw Error(SIGNIN_MSG);
    if(!isDashboardTab(s.href,c.dashboard))throw Error('The linked Grafana tab changed dashboard, time or filters. Click Use tab again; no email was sent.');
    if(s.scrollWidth>s.clientWidth+40)throw Error('Dashboard has horizontal overflow at the fixed capture width. Close its side drawer and retry.');
  }
  async function stable(label,percent){
    let last=null,clear=0,signature='',first=Date.now();
    while(Date.now()-first<35000){
      const s=await page('read');validate(s);last=s;
      const why=s.errors.length?s.errors[0]:s.missing[0]||(!s.visiblePanels?'loading panels':s.busy?'querying data':'');
      await progress(why?`${label}: ${why}`:label,percent);
      if(s.errors.length)throw Error('Grafana panel error — '+s.errors.join('; ').slice(0,600));
      const ok=s.ready==='complete'&&s.visiblePanels>0&&!s.busy&&!s.missing.length;
      const key=[s.scrollTop,s.contentEnd,s.visiblePanels,s.paintedCanvases,s.meaningful].join('|');
      clear=ok&&key===signature?clear+1:ok?1:0;signature=key;
      if(clear>=3&&Date.now()-first>=1400)return s;
      await sleep(700);
    }
    const reason=last?.missing?.join('; ')||(last?.busy?'Panels are still loading.':'No rendered Grafana panels in this part of the page.');
    throw Error('Screenshot blocked: '+reason+'. Keep the Grafana tab visible and retry Check screenshot. No blank report was emailed.');
  }
  function compositorPainted(ctx,region,top,bottom){
    const x=Math.max(0,Math.ceil(region.x)),y=Math.max(top,Math.ceil(region.y));
    const w=Math.min(width-x,Math.floor(region.width)),h=Math.min(bottom,Math.floor(region.bottom))-y;
    if(w<60||h<40)return true;
    const a=ctx.getImageData(x,y,w,h).data;let base=null,changed=0;
    const sx=Math.max(1,Math.floor(w/96)),sy=Math.max(1,Math.floor(h/48));
    for(let yy=0;yy<h;yy+=sy)for(let xx=0;xx<w;xx+=sx){const i=(yy*w+xx)*4;
      if(!base)base=[a[i],a[i+1],a[i+2]];
      if(Math.abs(a[i]-base[0])+Math.abs(a[i+1]-base[1])+Math.abs(a[i+2]-base[2])>14)changed++;
    }
    return changed>=3;
  }
  try{
    await progress('Preparing fixed-width dashboard capture',20);
    try{await chrome.debugger.attach(target,'1.3');attached=true;}catch(e){throw Error('Cannot attach screenshot capture. Close DevTools on this Grafana tab and retry. '+e.message);}
    await cmd('Page.enable');
    await cmd('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});
    // Failure to set the required viewport is fatal; do not silently use screen size.
    try{await cmd('Emulation.setFocusEmulationEnabled',{enabled:true});}catch{}
    try{await cmd('Page.setWebLifecycleState',{state:'active'});}catch{}
    await chrome.scripting.executeScript({target:{tabId},files:['capture-page.js']});
    started=true;
    let s=await page('start');validate(s);
    if(s.width!==width||s.height!==height)throw Error('Chrome did not apply the required 1600 × 1000 capture viewport. Screenshot not sent.');
    const originTop=s.rootTop;let discoveredEnd=0,discoverCount=0,previousTop=-1,stalled=0;
    // Walk the actual Grafana scroll container. This mounts lazy panels and finds
    // real content edges even when the document has a huge empty/min-height tail.
    await progress('Opening sections and finding dashboard content',26);
    // Scan every viewport, including blank gaps: jumping to the bottom could
    // skip lazy panels. The overall deadline bounds scans of pathological pages.
    for(let i=0;;i++){
      if(c.expandRows!==false){const r=await page('expand');if(r.count)await sleep(500);}
      await sleep(300);s=await page('read');validate(s);
      discoveredEnd=Math.max(discoveredEnd,s.contentEnd);discoverCount++;
      if(originTop+discoveredEnd>24000)throw Error('Measured dashboard content is '+Math.ceil(originTop+discoveredEnd)+' pixels tall (limit 24,000). Select As currently open and collapse sections before retrying.');
      if(s.scrollTop>=s.maxScroll-2)break;
      stalled=s.scrollTop<=previousTop+1?stalled+1:0;
      if(stalled>=3)throw Error('Dashboard scrolling is stuck at '+Math.round(s.scrollTop)+' of '+Math.round(s.maxScroll)+' pixels. Close dashboard overlays, keep the tab visible, and retry.');
      previousTop=s.scrollTop;
      await page('scroll',{top:Math.min(s.maxScroll,s.scrollTop+Math.max(150,(s.bottom-s.visibleTop)*.72))});
      await progress('Finding dashboard content · section '+(i+1),Math.min(35,27+i/3));
    }
    await log('info','Discovery completed: '+discoverCount+' steps; content '+Math.ceil(originTop+discoveredEnd)+'px; scroll extent '+Math.round(s.maxScroll)+'px.');
    s=await page('read');
    if(c.expandRows!==false&&s.collapsed.length)throw Error('Some dashboard rows could not be expanded: '+s.collapsed.join(', ')+'. Open them manually, select As currently open, and retry.');
    await page('scroll',{top:0});await sleep(500);
    s=await stable('Waiting for first charts to paint',38);
    discoveredEnd=Math.max(discoveredEnd,s.contentEnd);
    let end=Math.min(Math.ceil(originTop+discoveredEnd),Math.floor(originTop+s.maxScroll+s.bottom-s.rootTop));
    if(end>24000)throw Error('Expanded dashboard is over 24,000 pixels tall. Close unnecessary sections and use As currently open.');
    let covered=0,index=0;const panelsSeen=new Set(),noData=new Set();
    while(covered<end){
      if(index>=45)throw Error('Capture exceeded 45 parts; use fewer open sections.');
      if(index){
        const targetTop=Math.max(0,covered-originTop-(s.visibleTop-s.rootTop)-140);
        await page('scroll',{top:targetTop});await sleep(400);
        s=await stable('Rendering screenshot part '+(index+1),Math.min(78,40+38*covered/end));
      }
      for(const n of s.noData)noData.add(n);
      for(const r of s.canvasRegions)panelsSeen.add(r.panel);
      const newEnd=Math.min(Math.ceil(originTop+s.contentEnd),Math.floor(originTop+s.maxScroll+s.bottom-s.rootTop));
      if(newEnd>end+30)throw Error('Dashboard layout changed while being captured. Retry when its rows stop moving.');
      const mappedTop=originTop+s.scrollTop+(s.visibleTop-s.rootTop);
      const sourceTop=index?Math.round(s.rootTop+covered-originTop-s.scrollTop):0;
      if(index&&mappedTop>covered+2)throw Error('Could not capture consecutive dashboard content without a gap. Retry Check screenshot.');
      const take=Math.floor(Math.min(s.bottom-sourceTop,end-covered));
      if(take<1)throw Error('Grafana scrolling stopped before the end of the dashboard. Screenshot not sent.');
      await progress(`Capturing part ${index+1} · ${Math.round(100*covered/end)}% of dashboard`,Math.min(80,42+38*covered/end));
      let bitmap=null;
      for(let retry=0;retry<3;retry++){
        const screen=await cmd('Page.captureScreenshot',{format:'png',fromSurface:true,captureBeyondViewport:false});
        const bytes=Uint8Array.from(atob(screen.data),x=>x.charCodeAt(0));
        bitmap=await createImageBitmap(new Blob([bytes],{type:'image/png'}));
        if(bitmap.width!==width||bitmap.height!==height){bitmap.close();throw Error('Chrome returned unexpected screenshot dimensions; capture stopped.');}
        const scratch=new OffscreenCanvas(width,height),ctx=scratch.getContext('2d',{willReadFrequently:true});ctx.drawImage(bitmap,0,0);
        // Multiple canvas layers may overlap; a rendered underlying layer is enough.
        const failures=s.canvasRegions.filter(r=>!compositorPainted(ctx,r,Math.max(sourceTop,s.visibleTop),sourceTop+take));
        if(!failures.length)break;
        bitmap.close();bitmap=null;
        if(retry===2)throw Error('Screenshot blocked: Chrome captured empty chart pixels in '+failures[0].panel+'. Keep the dashboard tab visible, then retry Check screenshot.');
        await sleep(1000);s=await stable('Repainting blank screenshot charts',Math.min(80,42+38*covered/end));
      }
      bitmaps.push({bitmap,sy:sourceTop,h:take,dy:covered});covered+=take;index++;
    }
    if(!bitmaps.length)throw Error('No dashboard screenshot parts were captured.');
    await progress('Joining '+bitmaps.length+' screenshot parts',82);
    const joined=new OffscreenCanvas(width,Math.ceil(covered)),ctx=joined.getContext('2d');
    for(const t of bitmaps){ctx.drawImage(t.bitmap,0,t.sy,width,t.h,0,t.dy,width,t.h);t.bitmap.close();}
    bitmaps=[];
    let blob=await joined.convertToBlob({type:'image/png'}),ext='png';
    // Preserve 1600px width. Never silently scale a tall dashboard into unreadable text.
    if(blob.size>MAX_ATTACH_BYTES){for(const quality of [.9,.8,.7]){blob=await joined.convertToBlob({type:'image/jpeg',quality});ext='jpg';if(blob.size<=MAX_ATTACH_BYTES)break;}}
    if(blob.size>MAX_ATTACH_BYTES)throw Error('Full-width screenshot is too large for this email attachment. Close unnecessary sections; the image was not silently shrunk or emailed.');
    const b=new Uint8Array(await blob.arrayBuffer());let binary='';for(let i=0;i<b.length;i+=32768)binary+=String.fromCharCode(...b.subarray(i,i+32768));
    const meta={width,height:covered,tiles:index,expandedRows:s.expanded,chartPanels:panelsSeen.size,noDataPanels:[...noData],internalScroller:s.internal,
      startedAt:deadline-240000,finishedAt:Date.now(),rowMode:c.expandRows!==false?'all':'current',method:'viewport-tiles',appVersion:'3.7.5'};
    await log('info',`Screenshot checked: ${width} × ${covered}; ${index} parts; ${meta.chartPanels} chart panels; ${meta.expandedRows} rows opened; ${noData.size} explicitly report No data.`);
    return {data:btoa(binary),mime:blob.type,ext,meta,tabId};
  }finally{
    for(const t of bitmaps)try{t.bitmap.close();}catch{}
    if(started)try{await page('restore');}catch{}
    if(attached){
      try{await cmd('Emulation.setFocusEmulationEnabled',{enabled:false});}catch{}
      try{await cmd('Emulation.clearDeviceMetricsOverride');}catch{}
      try{await chrome.debugger.detach(target);}catch{}
    }
  }
}

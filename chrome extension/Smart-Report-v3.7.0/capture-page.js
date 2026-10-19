/* Runs only in the configured Grafana tab, in the extension isolated world.
 * No Grafana private React state, query data, cookies or authentication is read.
 * DOM changes are limited to scrolling, row toggles and temporary scroll CSS.
 */
(() => {
  'use strict';
  if (globalThis.__SR_CAPTURE_PAGE__) return;
  let session = null;
  const PANEL = [
    '.react-grid-item', '.panel-container', '[data-panelid]', '[data-viz-panel-key]',
    '[role="region"][aria-label$=" panel"]',
    '[data-testid="data-testid panel content"]', '[data-testid="panel content"]',
    '[data-testid="panel-content"]', '.panel-content'
  ].join(',');
  const ROW = [
    '.dashboard-row-header', '.dashboard-row__title', '.dashboard-row__title-wrap',
    '[data-testid*="dashboard-row-title"]', '[data-testid*="Dashboard row title"]',
    '[data-testid*="Row title"]', '[aria-label^="Expand row "]', '[aria-label^="Collapse row "]'
  ].join(',');
  const rect = e => { const r = e.getBoundingClientRect(); return { x:r.x, y:r.y, width:r.width, height:r.height, bottom:r.bottom, right:r.right }; };
  const displayed = e => { const r=rect(e), s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'; };
  const intersect = (r,a) => Math.max(0,Math.min(r.bottom,a.bottom)-Math.max(r.y,a.y))>24 && Math.max(0,Math.min(r.right,a.right)-Math.max(r.x,a.x))>40;
  function panels() {
    const all=[...document.querySelectorAll(PANEL)].filter(e=>{
      const r=rect(e);return displayed(e)&&r.width>=100&&r.height>=65;
    });
    // Outermost individual panel wrapper, not its content/legend children.
    return all.filter(e=>!all.some(p=>p!==e&&p.contains(e)));
  }
  function title(e) { return (e.querySelector('[data-testid*="Panel header"],.panel-title,h2,h3,header')?.textContent || e.getAttribute('aria-label') || e.getAttribute('data-panelid') || 'Untitled panel').trim().slice(0,120); }
  function findScroller() {
    const ps=panels(), candidates=new Set([document.scrollingElement]);
    for(const p of [...ps,...document.querySelectorAll(ROW)]) for(let e=p.parentElement;e;e=e.parentElement)candidates.add(e);
    let best=document.scrollingElement, score=-1;
    for(const e of candidates){
      if(!e||!displayed(e)||ps.some(p=>p.contains(e)))continue;
      const r=rect(e), root=e===document.scrollingElement;
      if(!root && (!/(auto|scroll)/.test(getComputedStyle(e).overflowY)||r.width<innerWidth*.5||e.clientHeight<180))continue;
      if(e.scrollHeight<=e.clientHeight+4)continue;
      const n=ps.filter(p=>e.contains(p)).length;
      const s=n*10000000+(root?0:5000000)+Math.min(r.width,innerWidth)*Math.min(e.clientHeight,innerHeight);
      if(s>score){score=s;best=e;}
    }
    return best;
  }
  function geometry() {
    const e=session.scroller, root=e===document.scrollingElement;
    if(!e.isConnected) throw Error('Grafana replaced its scroll container during capture. Retry the preview.');
    const r=root?{x:0,y:0,right:innerWidth,bottom:innerHeight}:rect(e);
    const top=root?0:Math.max(0,r.y+e.clientTop), bottom=root?innerHeight:Math.min(innerHeight,r.y+e.clientTop+e.clientHeight);
    let visibleTop=top;
    // Do not repeat sticky navigation or variable controls in every tile.
    for(const el of session.sticky){
      if(!el.isConnected||!displayed(el))continue;
      const z=rect(el);
      if(z.y<=top+160&&z.bottom>visibleTop&&z.height<180&&z.width>innerWidth*.5)visibleTop=z.bottom;
    }
    visibleTop=Math.min(visibleTop,bottom-100);
    return {rootTop:top,visibleTop,bottom,scrollTop:e.scrollTop,maxScroll:Math.max(0,e.scrollHeight-e.clientHeight),scrollHeight:e.scrollHeight,
      width:innerWidth,height:innerHeight,internal:!root,scrollWidth:e.scrollWidth,clientWidth:e.clientWidth};
  }
  function rowControls(){
    const out=[],seen=new Set();
    for(const el of document.querySelectorAll(ROW)){
      const button=el.matches('button')?el:el.querySelector('button[aria-expanded]')||el.closest('button[aria-expanded]');
      const ctl=button||el;
      if(!displayed(ctl)||seen.has(ctl))continue;
      // Avoid nested copies of the same legacy title wrapper.
      if(out.some(x=>x.el.contains(ctl)||ctl.contains(x.el)))continue;
      let collapsed=null;
      if(ctl.hasAttribute('aria-expanded'))collapsed=ctl.getAttribute('aria-expanded')==='false';
      else if(/^Expand row /i.test(ctl.getAttribute('aria-label')||''))collapsed=true;
      else if(/^Collapse row /i.test(ctl.getAttribute('aria-label')||''))collapsed=false;
      else {
        const header=ctl.closest('.dashboard-row,.dashboard-row-header')||ctl;
        if(header.querySelector('[data-testid*="angle-right"],.fa-caret-right,.fa-angle-right,[aria-label="angle-right"]'))collapsed=true;
        else if(header.querySelector('[data-testid*="angle-down"],.fa-caret-down,.fa-angle-down,[aria-label="angle-down"]'))collapsed=false;
        else if(/\(\s*\d+\s+panels?\s*\)/i.test(header.textContent))collapsed=true;
      }
      if(collapsed!==null){seen.add(ctl);out.push({el:ctl,collapsed,label:ctl.textContent.trim().slice(0,140)});}
    }
    return out;
  }
  function canvasPaint(el){
    if(el.width<20||el.height<10)return false;
    try{
      const sample=document.createElement('canvas');sample.width=96;sample.height=48;
      const c=sample.getContext('2d',{willReadFrequently:true});c.drawImage(el,0,0,96,48);
      const a=c.getImageData(0,0,96,48).data;
      let opaque=0,first=null,changes=0;
      for(let i=0;i<a.length;i+=4){
        if(a[i+3]<8)continue;opaque++;
        if(!first)first=[a[i],a[i+1],a[i+2],a[i+3]];
        else if(Math.abs(a[i]-first[0])+Math.abs(a[i+1]-first[1])+Math.abs(a[i+2]-first[2])+Math.abs(a[i+3]-first[3])>12)changes++;
      }
      // A transparent canvas is not a rendered time-series chart.
      return opaque>3&&(changes>1||opaque<a.length/4*.97);
    }catch{return null;} // e.g. a cross-origin/tainted canvas: checked in screenshot pixels instead
  }
  function read() {
    const g=geometry(), area={x:0,y:g.visibleTop,right:innerWidth,bottom:g.bottom};
    const list=panels(), visible=list.filter(e=>intersect(rect(e),area));
    const missing=[], errors=[], canvasRegions=[], noData=[];
    let busy=0, paintedCanvases=0, charts=0, meaningful=0;
    for(const p of visible){
      const name=title(p);
      const txt=p.innerText||'';
      const loading=[...p.querySelectorAll('[aria-busy="true"],.panel-loading,.loading-indicator,[aria-label="Panel loading bar"],[data-testid*="Panel loading"],[data-testid*="panel-loading"]')].filter(displayed);
      busy+=loading.length;
      const err=[...p.querySelectorAll('[data-testid*="Panel data error message"],[data-testid*="Panel status error"],[aria-label="Panel header error"],.panel-error')].filter(displayed);
      if(err.length)errors.push(name+': '+(err[0].getAttribute('title')||err[0].textContent||'query error').trim().slice(0,180));
      const hasNoData=/(^|\n)\s*(No data|No results|No data points|No data to show)\s*(\n|$)/i.test(txt);
      if(hasNoData){noData.push(name);meaningful++;continue;}
      const canvases=[...p.querySelectorAll('canvas')].filter(e=>displayed(e)&&rect(e).width>70&&rect(e).height>25);
      if(canvases.length){
        charts++;const checks=canvases.map(canvasPaint);
        if(checks.every(v=>v===false))missing.push(name+' (chart canvas is blank)');
        else {paintedCanvases+=checks.filter(v=>v===true).length;meaningful++;}
        for(const el of canvases)if(intersect(rect(el),area))canvasRegions.push({...rect(el),panel:name});
      }else{
        const svg=[...p.querySelectorAll('svg')].some(e=>rect(e).width>70&&rect(e).height>40&&e.querySelector('path,rect,circle,polyline'));
        const table=p.querySelector('table,[role="table"],.markdown-html');
        const clone=(p.querySelector('[data-testid*="panel content"],.panel-content')||p).cloneNode(true);
        for(const el of clone.querySelectorAll('header,h1,h2,h3,[data-testid*="Panel header"],.panel-title,.u-legend,[data-testid*="VizLegend"],button'))el.remove();
        const valueText=clone.textContent.trim();
        if(svg||table||/[0-9]/.test(valueText)||valueText.length>50)meaningful++;
        else missing.push(name+' (visualization has not rendered)');
      }
    }
    let end=0;
    const objects=[...list,...document.querySelectorAll(ROW)];
    for(const e of objects){if(displayed(e)&&session.scroller.contains(e))end=Math.max(end,rect(e).bottom-g.rootTop+g.scrollTop);}
    session.end=Math.max(session.end,end);
    const rows=rowControls();
    const login=!!document.querySelector('input[type="password"]')||/^\/login/.test(location.pathname);
    return {...g,href:location.href,login,ready:document.readyState,panels:list.length,visiblePanels:visible.length,meaningful,busy,missing,errors,noData,
      paintedCanvases,charts,canvasRegions,contentEnd:Math.ceil(session.end+16),rows:rows.length,collapsed:rows.filter(r=>r.collapsed).map(r=>r.label),expanded:session.expanded};
  }
  globalThis.__SR_CAPTURE_PAGE__=(op,arg={})=>{
    if(op==='start'){
      if(session)globalThis.__SR_CAPTURE_PAGE__('restore');
      const scroller=findScroller();
      const sticky=[...document.querySelectorAll('body *')].filter(e=>['fixed','sticky'].includes(getComputedStyle(e).position)&&!e.closest(PANEL));
      const style=document.createElement('style');style.textContent='html,body,*{scroll-behavior:auto!important;scroll-snap-type:none!important}';document.head.append(style);
      session={scroller,oldTop:scroller.scrollTop,oldLeft:scroller.scrollLeft,sticky,style,end:0,expanded:0};
      scroller.scrollTop=0;scroller.scrollLeft=0;
      return read();
    }
    if(!session)throw Error('Screenshot session was interrupted; run Check screenshot again.');
    if(op==='read')return read();
    if(op==='scroll'){
      session.scroller.scrollTop=Math.max(0,Number(arg.top)||0);
      return geometry();
    }
    if(op==='expand'){
      let count=0;
      for(const r of rowControls())if(r.collapsed){r.el.click();count++;}
      session.expanded+=count;return {count};
    }
    if(op==='resetEnd'){session.end=0;return read();}
    if(op==='restore'){
      const s=session;session=null;s.style.remove();
      if(s.scroller.isConnected){s.scroller.scrollTop=s.oldTop;s.scroller.scrollLeft=s.oldLeft;}
      return {restored:true};
    }
    throw Error('Unknown capture operation');
  };
})();

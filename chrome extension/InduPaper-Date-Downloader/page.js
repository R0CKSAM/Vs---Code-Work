// Self-contained so Chrome can serialize it into the site's MAIN world.
globalThis.induPage = async function(action='inspect',payload={}){
 try{
  const dates=[...document.querySelectorAll('input[type="date"]')];
  const candidates=dates.map(date=>{
   let form=date.parentElement;
   while(form&&form!==document.body&&!form.querySelector('.btn-download'))form=form.parentElement;
   const button=form?.querySelector('.btn-download');
   const fn=/^\s*(?:return\s+)?([A-Za-z_$][\w$]*)\(\s*\)\s*;?\s*$/.exec(button?.getAttribute('onclick')||'')?.[1];
   return {date,form,button,fn};
  }).filter(x=>x.date.id&&x.button&&x.fn&&typeof window[x.fn]==='function');
  if(candidates.length!==1){if(action==='status')return {ok:true,ready:false,busy:!!window.__induBatchBusy,task:window.__induTask||null};throw Error('This page needs one newspaper date form and PDF button. Wait for it to load, or open a newspaper page on InduPaper.');}
  const {date,form,button,fn}=candidates[0];
  const selects=[...form.querySelectorAll('select')];
  if(selects.some(x=>!x.id))throw Error('This newspaper has an unsupported edition selector.');
  const snapshot=()=>({title:form.querySelector('h2,h3')?.textContent.trim()||document.title.split(' Epaper')[0],
   path:location.pathname,slug:location.pathname.split('/').pop().replace(/\.html$/i,''),dateId:date.id,functionName:fn,date:date.value,
   fields:selects.map(s=>({id:s.id,label:[...form.querySelectorAll('label')].find(l=>l.htmlFor===s.id)?.textContent.trim()||s.id,value:s.value,
    options:[...s.options].map(o=>({value:o.value,text:o.textContent.trim(),disabled:o.disabled}))}))});
  if(action==='status')return {ok:true,ready:selects.every(s=>s.options.length>0),busy:!!window.__induBatchBusy||button.disabled,task:window.__induTask||null};
  const wait=ms=>new Promise(r=>setTimeout(r,ms));
  const choose=async(field,value)=>{
   const end=Date.now()+10000;
   while(![...field.options].some(o=>o.value===value&&!o.disabled)){
    if(Date.now()>end)throw Error('Chosen '+field.id+' edition is unavailable for this date.');await wait(200);
   }
   field.value=value;field.dispatchEvent(new Event('change',{bubbles:true}));await wait(350);
  };
  if(action==='inspect')return {ok:true,paper:snapshot()};
  if(action==='select'){
   if(window.__induBatchBusy||button.disabled)throw Error('Wait for the active PDF to finish before changing editions.');
   const field=selects.find(x=>x.id===payload.id);if(!field)throw Error('Edition selector changed; reopen the extension.');
   await choose(field,payload.value);return {ok:true,paper:snapshot()};
  }
  if(action!=='download')throw Error('Unknown page command.');
  if(payload.paper?.path!==location.pathname||payload.paper.dateId!==date.id||payload.paper.functionName!==fn)throw Error('The newspaper page changed. Return to the batch’s original newspaper page.');
  if(window.__induBatchBusy||button.disabled)throw Error('The website is already preparing a PDF. Wait before retrying.');
  window.__induBatchBusy=true;
  const task=window.__induTask={id:payload.attemptId||'legacy',date:payload.date,state:'working',downloadRequested:false,startedAt:Date.now()};
  const alertBefore=window.alert,errorBefore=console.error,fetchBefore=window.fetch;
  const originalPDF=window.jspdf?.jsPDF;let wrappedPDF;
  if(originalPDF){try{
   wrappedPDF=new Proxy(originalPDF,{construct(target,args){
    const document=Reflect.construct(target,args);const save=document.save;
    document.save=function(...values){task.downloadRequested=true;task.state='download-requested';return save.apply(this,values);};return document;
   }});window.jspdf.jsPDF=wrappedPDF;
  }catch{wrappedPDF=undefined;}}
  let issue='',detail='',http='';
  window.alert=text=>{issue=String(text);};
  console.error=(...args)=>{detail=args.map(x=>x?.message||String(x)).join(' ').slice(0,400);errorBefore.apply(console,args);};
  window.fetch=async(...args)=>{
   const response=await fetchBefore.apply(window,args);
   // Ads/analytics can legitimately return opaque status 0. Only the paper API matters.
   try{const url=new URL(args[0]?.url||String(args[0]),location.href);
    const paperApi=(url.hostname===location.hostname||url.hostname==='d3i9pcxc8oepjn.cloudfront.net')&&/\/(?:download|cities)(?:\/|$)/i.test(url.pathname);
    if(paperApi&&response.type!=='opaque'&&response.status>=400)http='Newspaper server returned HTTP '+response.status;
   }catch{}
   return response;
  };
  try{
   date.value=payload.date;date.dispatchEvent(new Event('change',{bubbles:true}));await wait(350);
   for(const field of selects){const selected=payload.selections.find(s=>s.id===field.id);if(!selected)throw Error('Choose every required edition selector.');await choose(field,selected.value);}
   for(const field of selects)if(field.value!==payload.selections.find(s=>s.id===field.id)?.value)throw Error('The website changed the selected edition; no PDF was requested.');
   await window[fn]();
   if(issue||http)throw Error([issue,http,detail].filter(Boolean).join(' '));
   task.state='complete';return {ok:true,downloadRequested:task.downloadRequested};
  }catch(error){if(http&&!String(error.message||error).includes(http))throw Error(String(error.message||error)+' '+http);throw error;
  }finally{window.alert=alertBefore;console.error=errorBefore;window.fetch=fetchBefore;window.__induBatchBusy=false;if(wrappedPDF&&window.jspdf.jsPDF===wrappedPDF)window.jspdf.jsPDF=originalPDF;}
 }catch(error){
  const text=error.message||String(error),status=Number(/HTTP (\d+)/.exec(text)?.[1])||null;
  const task=window.__induTask,ours=action==='download'&&task?.id===(payload.attemptId||'legacy');
  const failure={ok:false,error:text,httpStatus:status,downloadRequested:!!(ours&&task.downloadRequested),
   transient:status?[408,425,429].includes(status)||status>=500:/failed to fetch|network|connection|load failed|could not fetch|error creating pdf|timed? ?out|\[object Event\]/i.test(text)};
  if(ours){task.state='failed';task.error=text;task.failure=failure;}return failure;
 }
};

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
  if(candidates.length!==1)throw Error('This page needs one newspaper date form and PDF button. Wait for it to load, or open a newspaper page on InduPaper.');
  const {date,form,button,fn}=candidates[0];
  const selects=[...form.querySelectorAll('select')];
  if(selects.some(x=>!x.id))throw Error('This newspaper has an unsupported edition selector.');
  const snapshot=()=>({title:form.querySelector('h2,h3')?.textContent.trim()||document.title.split(' Epaper')[0],
   path:location.pathname,slug:location.pathname.split('/').pop().replace(/\.html$/i,''),dateId:date.id,functionName:fn,date:date.value,
   fields:selects.map(s=>({id:s.id,label:[...form.querySelectorAll('label')].find(l=>l.htmlFor===s.id)?.textContent.trim()||s.id,value:s.value,
    options:[...s.options].map(o=>({value:o.value,text:o.textContent.trim(),disabled:o.disabled}))}))});
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
  const alertBefore=window.alert,errorBefore=console.error,fetchBefore=window.fetch;
  let issue='',detail='',http='';
  window.alert=text=>{issue=String(text);};
  console.error=(...args)=>{detail=args.map(x=>x?.message||String(x)).join(' ').slice(0,400);errorBefore.apply(console,args);};
  window.fetch=async(...args)=>{const response=await fetchBefore.apply(window,args);if(!response.ok)http='Website returned HTTP '+response.status;return response;};
  try{
   date.value=payload.date;date.dispatchEvent(new Event('change',{bubbles:true}));await wait(350);
   for(const field of selects){const selected=payload.selections.find(s=>s.id===field.id);if(!selected)throw Error('Choose every required edition selector.');await choose(field,selected.value);}
   for(const field of selects)if(field.value!==payload.selections.find(s=>s.id===field.id)?.value)throw Error('The website changed the selected edition; no PDF was requested.');
   await window[fn]();
   if(issue||http)throw Error([issue,http,detail].filter(Boolean).join(' '));
   return {ok:true};
  }finally{window.alert=alertBefore;console.error=errorBefore;window.fetch=fetchBefore;window.__induBatchBusy=false;}
 }catch(error){return {ok:false,error:error.message||String(error)};}
};

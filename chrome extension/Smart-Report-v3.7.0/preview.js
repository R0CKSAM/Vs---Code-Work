'use strict';
const $=id=>document.getElementById(id);
async function request(action,extra={}){const r=await chrome.runtime.sendMessage({action,...extra});if(!r?.ok)throw Error(r?.error||'Extension did not respond');return r.result;}
(async()=>{
  const r=await request('PREVIEW_DATA');
  if(!r.image)throw Error('No screenshot preview is available. Open Smart Report and select Check screenshot.');
  $('image').src=r.image;
  await $('image').decode();
  $('meta').textContent=`${r.meta.width} × ${r.meta.height} pixels · ${r.meta.tiles} captured parts · ${r.meta.chartPanels} chart panels · ${r.meta.rowMode==='all'?'All sections':'As currently open'}`;
  $('download').href=r.image;$('download').download='Smart-Report-preview.'+(r.image.startsWith('data:image/png')?'png':'jpg');$('download').hidden=false;
  $('approve').disabled=false;
  if(r.approved){$('approve').textContent='Layout approved';$('approve').disabled=true;}
  $('approve').onclick=async()=>{try{await request('APPROVE_CAPTURE',{previewId:r.previewId});$('approve').textContent='Layout approved';$('approve').disabled=true;$('message').textContent='Layout approved. Return to Smart Report, send one test, and verify the attachment before starting reports.';}catch(e){$('message').textContent=e.message;$('message').className='error';}};
})().catch(e=>{$('message').textContent=e.message;$('message').className='error';});
$('zoom').onclick=()=>{document.body.classList.toggle('actual');$('zoom').textContent=document.body.classList.contains('actual')?'Fit to screen':'Actual size';};

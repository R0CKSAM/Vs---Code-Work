const $=id=>document.getElementById(id);let tabId=null,paper=null,changing=false,commandRunning=false,uiError='';
const compatible=chrome.runtime.getManifest().version==='1.2.0';
const active=['queued','retrying','recovering','preparing','waiting','downloading'];
async function page(action='inspect',payload={}){
 const [r]=await chrome.scripting.executeScript({target:{tabId},world:'MAIN',func:induPage,args:[action,payload]});
 if(!r?.result?.ok)throw Error(r?.result?.error||'Could not read the newspaper page. Wait for it to load and reopen the extension.');return r.result.paper;
}
function fields(info){
 paper=info;$('paperName').textContent=info.title+' · InduPaper';$('editions').replaceChildren();
 for(const field of info.fields){
  const label=document.createElement('label');label.textContent=field.label;
  const select=document.createElement('select');select.dataset.field=field.id;
  for(const item of field.options){const o=document.createElement('option');o.value=item.value;o.textContent=item.text;o.disabled=item.disabled;select.append(o);}
  select.value=field.value;select.onchange=async()=>{changing=true;$('settings').disabled=true;$('startBatch').disabled=true;
   try{fields(await page('select',{id:field.id,value:select.value}));uiError='';}
   catch(e){uiError=e.message;}finally{changing=false;await render();}
  };label.append(select);$('editions').append(label);
 }
}
async function render(){if(!compatible)return;const {job:j}=await chrome.storage.local.get('job');
 const busy=j&&active.includes(j.phase);$('settings').disabled=!!busy||changing||commandRunning;$('startBatch').disabled=!tabId||!paper||!!busy||changing||commandRunning;
 $('pause').disabled=!busy||commandRunning;$('resume').disabled=j?.phase!=='paused'||commandRunning;$('skip').disabled=!['paused','retrying'].includes(j?.phase)||commandRunning;
 const path=j?.paper?.path||'/times-of-india.html';
 if(!j||(!busy&&j.phase==='done'&&paper?.path!==path))return;
 $('status').textContent=j.phase==='retrying'?`Automatic retry ${j.retryCount||1}/3 in ${Math.max(0,Math.ceil(((j.nextAt||Date.now())-Date.now())/1000))}s`:{queued:'Next date scheduled',recovering:'Restoring newspaper tab…',preparing:'Creating PDF…',waiting:'Waiting for Chrome download…',downloading:'Saving PDF…',paused:'Paused',done:'Batch finished'}[j.phase]||j.phase;
 $('progress').max=j.dates.length;$('progress').value=j.index;
 const saved=j.history.filter(h=>h.status==='saved').length,skipped=j.history.filter(h=>h.status==='skipped').length;
 $('detail').textContent=`${j.index} / ${j.dates.length} dates processed · ${saved} saved · ${skipped} skipped · ${j.paper?.title||'Times of India'} · ${j.edition||j.city||'Edition not selected'}${j.dates[j.index]?' · '+j.dates[j.index]:''}${j.pauseRequested?' · pausing after this file':''}`;
 $('error').textContent=uiError||j.error||'';$('error').style.color=j.phase==='retrying'?'#855400':'#ae251d';$('history').textContent=j.history.slice(-4).map(h=>`${h.date}: ${h.status}`).join(' · ');
}
async function command(action){if(commandRunning)return;commandRunning=true;uiError='';await render();try{
 const selections=[...document.querySelectorAll('[data-field]')].map(s=>({id:s.dataset.field,value:s.value}));
 const r=await chrome.runtime.sendMessage({action,tabId,selections,start:$('start').value,end:$('end').value});if(!r.ok)throw Error(r.error);await render();
}catch(e){uiError=e.message;}finally{commandRunning=false;await render();}}
async function init(){
 if(!compatible){
  $('connection').textContent='Update pending: open chrome://extensions and Reload InduPaper Date Downloader, then reopen this popup.';
  $('settings').disabled=true;for(const id of ['startBatch','pause','resume','skip'])$(id).disabled=true;return;
 }
 for(const id of ['pause','resume','skip']){$(id).disabled=true;$(id).onclick=()=>{if(id==='resume'&&!confirm('Resume the saved batch? Chrome download history will be checked before requesting another PDF.'))return;if(id==='skip'&&!confirm('Skip this date and continue automatically with the next date?'))return;command(id);};}
 $('startBatch').disabled=true;$('startBatch').onclick=()=>command('start');
 try{const [t]=await chrome.tabs.query({active:true,currentWindow:true});const url=new URL(t?.url||'about:blank');
 if(url.protocol!=='https:'||!['indupaper.com','www.indupaper.com'].includes(url.hostname))throw Error('Open your chosen newspaper page on InduPaper, then reopen this extension.');
 tabId=t.id;fields(await page());
 $('start').value=$('end').value=paper.date;$('connection').textContent='Connected to '+paper.title;
 }catch(e){tabId=null;$('connection').textContent=e.message;}
 await render();
}
chrome.storage.onChanged.addListener(()=>render());init();setInterval(()=>render(),1000);

const $=id=>document.getElementById(id);let tabId=null,paper=null,changing=false;
const active=['queued','preparing','waiting','downloading'];
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
   try{fields(await page('select',{id:field.id,value:select.value}));$('error').textContent='';}
   catch(e){$('error').textContent=e.message;}finally{changing=false;await render();}
  };label.append(select);$('editions').append(label);
 }
}
async function render(){const {job:j}=await chrome.storage.local.get('job');
 const busy=j&&active.includes(j.phase);$('settings').disabled=!!busy||changing;$('startBatch').disabled=!tabId||!paper||!!busy||changing;
 $('pause').disabled=!busy;$('resume').disabled=j?.phase!=='paused';$('skip').disabled=j?.phase!=='paused';
 const path=j?.paper?.path||'/times-of-india.html';
 if(!j||(!busy&&j.phase==='done'&&paper?.path!==path))return;
 $('status').textContent={queued:'Next date scheduled',preparing:'Creating PDF…',waiting:'Waiting for Chrome download…',downloading:'Saving PDF…',paused:'Paused',done:'Batch finished'}[j.phase]||j.phase;
 $('progress').max=j.dates.length;$('progress').value=j.index;
 $('detail').textContent=`${j.index} / ${j.dates.length} dates processed · ${j.paper?.title||'Times of India'} · ${j.edition||j.city}${j.dates[j.index]?' · '+j.dates[j.index]:''}${j.pauseRequested?' · pausing after this file':''}`;
 $('error').textContent=j.error||'';$('history').textContent=j.history.slice(-4).map(h=>`${h.date}: ${h.status}`).join(' · ');
}
async function command(action){try{
 const selections=[...document.querySelectorAll('[data-field]')].map(s=>({id:s.dataset.field,value:s.value}));
 const r=await chrome.runtime.sendMessage({action,tabId,selections,start:$('start').value,end:$('end').value});if(!r.ok)throw Error(r.error);await render();
}catch(e){$('error').textContent=e.message;}}
async function init(){
 if(chrome.runtime.getManifest().version!=='1.1.1'){
  $('connection').textContent='Update pending: open chrome://extensions and Reload InduPaper Date Downloader, then reopen this popup.';
  $('settings').disabled=true;for(const id of ['startBatch','pause','resume','skip'])$(id).disabled=true;return;
 }
 for(const id of ['pause','resume','skip']){$(id).disabled=true;$(id).onclick=()=>{if(id==='resume'&&!confirm('Check the page and Downloads first. Retry can create another copy if the previous download already succeeded.'))return;if(id==='skip'&&!confirm('Skip this date and leave it out of the downloaded set?'))return;command(id);};}
 $('startBatch').disabled=true;$('startBatch').onclick=()=>command('start');
 try{const [t]=await chrome.tabs.query({active:true,currentWindow:true});const url=new URL(t?.url||'about:blank');
 if(url.protocol!=='https:'||!['indupaper.com','www.indupaper.com'].includes(url.hostname))throw Error('Open your chosen newspaper page on InduPaper, then reopen this extension.');
 tabId=t.id;fields(await page());
 $('start').value=$('end').value=paper.date;$('connection').textContent='Connected to '+paper.title;
 }catch(e){tabId=null;$('connection').textContent=e.message;}
 await render();
}
chrome.storage.onChanged.addListener(()=>render());init();

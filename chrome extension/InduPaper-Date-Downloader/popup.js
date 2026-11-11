const $=id=>document.getElementById(id);let tabId=null;
const active=['queued','preparing','waiting','downloading'];
async function render(){const {job:j}=await chrome.storage.local.get('job');if(!j)return;
 $('status').textContent={queued:'Next date scheduled',preparing:'Creating PDF…',waiting:'Waiting for Chrome download…',downloading:'Saving PDF…',paused:'Paused',done:'Batch finished'}[j.phase]||j.phase;
 $('progress').max=j.dates.length;$('progress').value=j.index;
 $('detail').textContent=`${j.index} / ${j.dates.length} dates processed · ${j.city}${j.dates[j.index]?' · '+j.dates[j.index]:''}${j.pauseRequested?' · pausing after this file':''}`;
 $('error').textContent=j.error||'';$('settings').disabled=active.includes(j.phase);$('startBatch').disabled=!tabId||active.includes(j.phase);
 $('pause').disabled=!active.includes(j.phase);$('resume').disabled=j.phase!=='paused';$('skip').disabled=j.phase!=='paused';
 $('history').textContent=j.history.slice(-4).map(h=>`${h.date}: ${h.status}`).join(' · ');
}
async function command(action){try{
 const r=await chrome.runtime.sendMessage({action,tabId,city:$('city').value,start:$('start').value,end:$('end').value});if(!r.ok)throw Error(r.error);await render();
}catch(e){$('error').textContent=e.message;}}
async function init(){
 for(const id of ['pause','resume','skip']){$(id).disabled=true;$(id).onclick=()=>{if(id==='resume'&&!confirm('Check the page and Downloads first. Retry can create another copy if the previous download already succeeded.'))return;if(id==='skip'&&!confirm('Skip this date and leave it out of the downloaded set?'))return;command(id);};}
 $('startBatch').disabled=true;$('startBatch').onclick=()=>command('start');
 try{const [t]=await chrome.tabs.query({active:true,currentWindow:true});
 if(!/^https:\/\/(www\.)?indupaper\.com\/times-of-india\.html(?:[?#]|$)/.test(t?.url||''))throw Error('Open the InduPaper Times of India tab, then reopen this extension.');
 const [r]=await chrome.scripting.executeScript({target:{tabId:t.id},func:()=>({date:document.getElementById('TOIDate')?.value,city:document.getElementById('TOICity')?.value,options:[...(document.getElementById('TOICity')?.options||[])].map(o=>({value:o.value,text:o.textContent}))})});
 if(!r.result?.options.length)throw Error('Wait for the city list to load, then reopen the extension.');
 tabId=t.id;for(const item of r.result.options){const o=document.createElement('option');o.value=item.value;o.textContent=item.text;$('city').append(o);}
 $('city').value=r.result.city;$('start').value=$('end').value=r.result.date;
 $('connection').textContent='Connected to your newspaper tab';$('startBatch').disabled=false;
 }catch(e){$('connection').textContent=e.message;}
 await render();
}
chrome.storage.onChanged.addListener(()=>render());init();

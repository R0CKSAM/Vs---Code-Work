const $=id=>document.getElementById(id);
const parse=s=>s.split(/\r?\n/).map(x=>x.trim()).filter(Boolean);
const uid=()=>`${Date.now()}-${Math.random().toString(36).slice(2)}`;
async function tab(){const [t]=await chrome.tabs.query({active:true,currentWindow:true});if(!t?.url||!/^https:\/\/(chatgpt\.com|chat\.openai\.com)\//.test(t.url))throw Error('Open a ChatGPT tab first.');return t;}
async function send(action){const t=await tab();const r=await chrome.tabs.sendMessage(t.id,{action,tabId:t.id});if(!r?.ok)throw Error(r?.error||'Extension did not acknowledge command. Reload ChatGPT and try again.');}
async function refresh(){const d=await chrome.storage.local.get(['prompts','index','phase','error','pending','activity','ownerTabId','manualDone']);const lines=d.prompts||[],i=d.index||0;
 $('status').textContent=d.phase||'idle';$('progress').textContent=`${Math.min(i,lines.length)} / ${lines.length}`;
 const frame=lines[i]||'';const label=frame.includes('||')?frame.split('||')[0].trim():`Queue row ${i+1}`;
 $('detail').textContent=[`Row ${Math.min(i+1,lines.length)}/${lines.length||0}: ${label}`,d.pending?`Pending: ${d.pending.state}`:'No pending frame','All rows auto-submit when the composer shows the enabled up-arrow.',d.activity||'',d.error||''].filter(Boolean).join('\n');
 $('complete').disabled=!d.pending;$('retry').disabled=!d.pending; $('setRow').disabled=!!d.pending || d.phase==='running';
}
async function op(fn){try{await fn()}catch(e){$('detail').textContent='Error: '+e.message;return;}await refresh();}
async function replaceQueue(master,prompts,filename){
 if(!prompts.length)throw Error('No prompts to save.');
 const old=await chrome.storage.local.get(['phase','pending']);
 if((old.phase==='running'||old.pending)&&!confirm('This replaces the current queue and resets its position. ChatGPT generation is NOT cancelled. Continue only if no image is generating.'))return false;
 try{await send('PAUSE');}catch{}
 await chrome.storage.local.set({master,prompts,index:0,phase:'idle',pending:null,queueId:uid(),ownerTabId:null,manualDone:true,manualStartIndex:0,error:'',activity:`Loaded ${prompts.length} rows from ${filename}. First: ${prompts[0].split('||')[0].trim()}.`});
 return true;
}
$('setRow').onclick=()=>op(async()=>{
 const d=await chrome.storage.local.get(['prompts','phase','pending']);
 if(d.phase==='running'||d.pending)throw Error('Pause and resolve any pending frame before changing next row.');
 const row=Number($('startRow').value),total=(d.prompts||[]).length;
 if(!Number.isInteger(row)||row<1||row>total)throw Error(`Row must be between 1 and ${total}.`);
 if(!confirm(`Set next prompt to imported row ${row}? First ${row-1} rows will be treated as already completed. Verify their images exist.`))return;
 await chrome.storage.local.set({index:row-1,manualStartIndex:row-1,manualDone:true,phase:'paused',pending:null,error:'',activity:`Next row set to ${row}/${total}. Resume to submit.`});
});
$('save').onclick=()=>op(async()=>{
 const prompts=parse($('prompts').value),master=$('master').value.trim();
 const existing=await chrome.storage.local.get(['prompts','master']);
 if(JSON.stringify(prompts)===JSON.stringify(existing.prompts||[])&&master===(existing.master||''))return;
 await replaceQueue(master,prompts,'text inputs');
});
$('start').onclick=()=>op(()=>send('START'));
$('pause').onclick=()=>op(()=>send('PAUSE'));
$('resume').onclick=()=>op(()=>send('RESUME'));
$('complete').onclick=()=>op(async()=>{if(confirm('Only mark complete if you SEE the finished image for this frame. Continue?'))await send('COMPLETE');});
$('retry').onclick=()=>op(async()=>{if(confirm('Retry may generate a DUPLICATE. Have you verified that the current prompt was NOT accepted/generated?'))await send('RETRY');});
$('reset').onclick=()=>op(async()=>{if(confirm('Reset to FIRST imported row? Do this only when ChatGPT is idle.'))await send('RESET');});
$('file').onchange=async e=>{
 const f=e.target.files?.[0];if(!f)return;
 try{const result=await StoryboardImport.read(f);const d=await chrome.storage.local.get(['master']);const master=result.master!==null?result.master:(d.master||'');
 if(!await replaceQueue(master,result.prompts,f.name))return;
 $('master').value=master;$('prompts').value=result.prompts.join('\n');$('importStatus').textContent=`Loaded ${result.count} frames in FILE ROW ORDER. First: ${result.prompts[0].split('||')[0].trim()}.`;await refresh();
 }catch(e){$('importStatus').textContent='Import error: '+e.message;}
};
(async()=>{const d=await chrome.storage.local.get(['master','prompts']);$('master').value=d.master||'';$('prompts').value=(d.prompts||[]).join('\n');await refresh();setInterval(refresh,1500);})();

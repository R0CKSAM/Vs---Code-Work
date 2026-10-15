/* v16: lifecycle observed in the user's diagnostic log. No message-count/image-count assumptions. */
(()=>{
 if(window.__storyboardV16)return;window.__storyboardV16=true;
 const TICK=700, READY_MS=900, FINISH_MS=2500, UNCERTAIN_MS=15000, MAX_WAIT=18*60*1000;
 let ticker=null,busy=false;
 const keys=['master','prompts','index','phase','pending','error','activity','ownerTabId','queueId'];
 const get=()=>chrome.storage.local.get(keys),put=o=>chrome.storage.local.set(o);
 const qs=(s,r=document)=>[...r.querySelectorAll(s)];
 const visible=e=>!!(e&&e.isConnected&&e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden');
 const edit=()=>qs('#prompt-textarea,[data-testid="prompt-textarea"],[contenteditable="true"][role="textbox"],textarea').find(visible);
 const value=e=>(e?.value??e?.innerText??'').trim();
 const norm=x=>(x||'').replace(/\s+/g,' ').trim();
 const same=(e,s)=>norm(value(e))===norm(s);
 const aria=b=>(b?.getAttribute('aria-label')||'').trim();
 const generatingControl=()=>qs('button').some(b=>visible(b)&&/^(stop|stop generating|stop response)$/i.test(aria(b)));
 const snakeIndicator=()=>qs('button[aria-label]').some(b=>visible(b)&&/play snake while your image is generating/i.test(aria(b)));
 const previews=()=>qs('button[data-testid="generated-image-preview"],button[aria-label^="Generated image "]').filter(visible);
 const editorScope=e=>e?.closest('form')||e?.closest('[data-testid="composer"]')||e?.parentElement?.parentElement?.parentElement;
 function sendButton(){
   const e=edit();if(!e||!value(e)||generatingControl())return null;
   const scope=editorScope(e);if(!scope)return null;
   // Verified from uploaded browser log: aria="Send", type="submit", enabled.
   const matches=qs('button[aria-label="Send"][type="submit"],button[aria-label="Send"],button[data-testid="send-button"]',scope)
     .filter(b=>visible(b)&&!b.disabled&&b.getAttribute('aria-disabled')!=='true');
   return matches.length===1?matches[0]:null;
 }
 const fingerprint=()=>previews().map(b=>{
   const img=b.querySelector('img');return [(img?.currentSrc||img?.src||'').slice(-160),b.getAttribute('aria-label')].join('|');
 });
 const idle=()=>!generatingControl()&&!snakeIndicator();
 function insert(e,s){
   e.focus();
   if(e.tagName==='TEXTAREA'){
     const setter=Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value')?.set;
     setter?setter.call(e,s):e.value=s;
   }else{
     e.replaceChildren();
     const r=document.createRange(),sel=window.getSelection();r.selectNodeContents(e);r.collapse(true);sel.removeAllRanges();sel.addRange(r);
     if(!document.execCommand('insertText',false,s))e.textContent=s;
   }
   e.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:s}));
 }
 function build(line,master){const k=line.indexOf('||');const label=k>=0?line.slice(0,k).trim():'';const scene=k>=0?line.slice(k+2).trim():line;
   return [master,label?`Frame: ${label}`:'',`Scene: ${scene}`,'Generate exactly ONE individual 16:9 image, not a contact sheet.'].filter(Boolean).join('\n\n');
 }
 function stop(){if(ticker)clearInterval(ticker);ticker=null;}
 async function pause(reason){stop();await put({phase:'paused',error:reason,activity:'Paused safely; inspect this frame before continuing.'});}
 async function tick(){
  if(busy)return;busy=true;
  try{
   const s=await get();if(s.phase!=='running')return;
   const list=s.prompts||[],i=s.index||0;
   if(i>=list.length){stop();await put({phase:'done',pending:null,activity:'All imported frames completed.',error:''});return;}
   if(s.ownerTabId!=null){const owner=await chrome.runtime.sendMessage({action:'MY_TAB_ID'});if(owner?.tabId!==s.ownerTabId)return;}
   const e=edit();if(!e){await pause('Composer not found. Refresh ChatGPT.');return;}
   const now=Date.now();let p=s.pending;
   if(!p){
     if(!idle()){await put({activity:'Existing generation detected. Waiting before preparing another prompt.'});return;}
     if(value(e)){await pause('Unsent text exists in composer. Clear manually only after checking it.');return;}
     p={queueId:s.queueId,state:'prepared',prompt:build(list[i],s.master||''),baseline:fingerprint(),baselineHadPreview:previews().length>0,
        preparedAt:now,sendReadyAt:0,clickedAt:0,editorEmptied:false,sawBusy:false,sawPreviewDisappear:false,sawPreviewReturn:false,
        sawNewPreview:false,completeSince:0};
     await put({pending:p,error:'',activity:`Row ${i+1}: pasting prompt.`});
     insert(e,p.prompt);
     if(!same(e,p.prompt)){await pause('Pasted prompt could not be verified. Nothing submitted.');return;}
     await put({activity:`Row ${i+1}: pasted; awaiting enabled Send button.`});return;
   }
   if(p.queueId!==s.queueId){await pause('Queue was replaced during a pending frame.');return;}
   if(p.state==='prepared'){
     if(!same(e,p.prompt)){
       if(!value(e) && !idle()){
         p={...p,state:'waiting',clickedAt:now,editorEmptied:true,sawBusy:true};
         await put({pending:p,activity:'Observed prompt leave editor during generation; tracking result.'});return;
       }
       await pause('Prepared text changed or disappeared. Inspect the conversation before resuming.');return;
     }
     const b=sendButton();
     if(!b){if(p.sendReadyAt)await put({pending:{...p,sendReadyAt:0}});
       await put({activity:'Prompt ready; waiting for aria=Send submit button. Not clicking voice/stop.'});return;}
     if(!p.sendReadyAt){await put({pending:{...p,sendReadyAt:now},activity:'Enabled Send detected; stabilizing.'});return;}
     if(now-p.sendReadyAt<READY_MS)return;
     const b2=sendButton();if(!b2)return;
     // Save first: a transient exception must NEVER cause a second click.
     p={...p,state:'waiting',clickedAt:now,editorEmptied:false};
     await put({pending:p,activity:`Row ${i+1}: clicked verified Send button once; awaiting generation lifecycle.`});
     b2.click();return;
   }
   if(p.state!=='waiting'){await pause('Unknown state.');return;}
   const submittedTextGone=!same(e,p.prompt) && !value(e);
   const isBusy=generatingControl()||snakeIndicator();
   const prev=fingerprint();
   let changed=false;
   const update={...p};
   if(submittedTextGone&&!p.editorEmptied){update.editorEmptied=true;changed=true;}
   if(isBusy&&!p.sawBusy){update.sawBusy=true;changed=true;}
   // Diagnostic evidence: existing preview disappears during image creation and reappears at completion.
   if(p.baselineHadPreview&&previews().length===0&&!p.sawPreviewDisappear){update.sawPreviewDisappear=true;changed=true;}
   if(p.sawPreviewDisappear&&previews().length>0&&!p.sawPreviewReturn){update.sawPreviewReturn=true;changed=true;}
   if(prev.some(x=>!p.baseline.includes(x))&&!p.sawNewPreview){update.sawNewPreview=true;changed=true;}
   const confirmsSubmission=update.editorEmptied&&(update.sawBusy||update.sawPreviewDisappear||update.sawNewPreview);
   const confirmsOutput=update.sawPreviewReturn||update.sawNewPreview;
   // Image output must be present, generator idle, and submission observed. Never count page-wide images.
   const complete=confirmsSubmission&&confirmsOutput&&previews().length>0&&idle()&&now-p.clickedAt>=3500;
   if(complete){
     if(!p.completeSince){update.completeSince=now;changed=true;}
     if(now-(update.completeSince||now)>=FINISH_MS){await put({index:i+1,pending:null,error:'',activity:`Completed row ${i+1}; proceeding to next imported row.`});return;}
   }else if(p.completeSince){update.completeSince=0;changed=true;}
   if(changed)await put({pending:update});
   await put({activity:`Row ${i+1} | editor cleared=${update.editorEmptied} | busy observed=${update.sawBusy} | preview disappeared=${update.sawPreviewDisappear} | preview returned=${update.sawPreviewReturn} | new preview=${update.sawNewPreview} | current previews=${previews().length} | idle=${idle()}.`});
   if(now-p.clickedAt>UNCERTAIN_MS && !update.editorEmptied && same(e,p.prompt)){await pause('Send clicked but prompt remains in editor. Check whether submission failed; no automatic retry.');return;}
   if(now-p.clickedAt>MAX_WAIT){await pause('Output not confirmed after 18 minutes. If image is complete, use Mark frame complete.');return;}
  }catch(err){await pause(`Unexpected queue error: ${err?.message||err}`);}finally{busy=false;}
 }
 function start(){stop();ticker=setInterval(tick,TICK);tick();}
 chrome.runtime.onMessage.addListener((msg,_sender,respond)=>{
  (async()=>{const s=await get();switch(msg.action){
   case 'START':case 'RESUME':{
     if(!s.prompts?.length)throw Error('Import or save prompts first.');
     if(s.phase==='done')throw Error('Queue complete; import new file or Reset.');
     if(s.pending&&s.ownerTabId!=null&&s.ownerTabId!==msg.tabId)throw Error('Pending frame belongs to another ChatGPT tab.');
     await put({phase:'running',ownerTabId:msg.tabId,error:'',activity:s.pending?'Resuming observation; no duplicate click.':'Preparing next row.'});start();break;
   }
   case 'PAUSE':stop();await put({phase:'paused',activity:'Paused; pending frame preserved.'});break;
   case 'COMPLETE':if(!s.pending)throw Error('No pending frame.');stop();await put({index:(s.index||0)+1,pending:null,phase:'paused',activity:'Manually confirmed complete. Resume for next row.',error:''});break;
   case 'RETRY':if(!s.pending)throw Error('No pending frame.');if(!idle())throw Error('Generation may still be active.');stop();await put({pending:null,phase:'paused',activity:'Retry armed, only after verifying frame not generated.'});break;
   case 'RESET':stop();await put({phase:'idle',index:0,pending:null,error:'',activity:'Reset to first imported row.'});break;
  }respond({ok:true});})().catch(e=>respond({ok:false,error:e.message}));return true;
 });
 get().then(s=>{if(s.phase==='running')start();});
})();

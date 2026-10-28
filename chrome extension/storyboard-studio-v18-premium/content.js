/* v16: lifecycle observed in the user's diagnostic log. No message-count/image-count assumptions. */
(()=>{
 if(window.__storyboardV16)return;window.__storyboardV16=true;
 const TICK=700, READY_MS=900, FINISH_MS=2500, UNCERTAIN_MS=15000, MAX_WAIT=18*60*1000;
 const RESTORE_DELAY=1400, MAX_RESTORES=3, COMPOSER_WAIT=10000;
 let ticker=null,busy=false,positioning=false;
 const keys=['master','prompts','index','phase','pending','error','activity','ownerTabId','queueId','frameHistory','autoDownload'];
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
 function messageKey(element){return element?.getAttribute('data-message-id')||element?.closest('[data-message-id]')?.getAttribute('data-message-id')||element?.closest('article')?.getAttribute('data-testid')||'';}
 function assistantMessages(){
   const messages=qs('[data-message-author-role="assistant"]');
   return {keys:messages.map(messageKey).filter(Boolean).slice(-16),lastId:messageKey(messages.at(-1))};
 }
 function previewOwner(button){return messageKey(button.closest('[data-message-author-role="assistant"]')||button.closest('article')?.querySelector('[data-message-author-role="assistant"]'));}
 function previewAsset(button){
   const img=button.querySelector('img'),src=img?.currentSrc||img?.src||'';if(!src)return '';
   try{const url=new URL(src,location.href);if(!/^https?:$/.test(url.protocol))return src;
     for(const name of [...url.searchParams.keys()])if(/^(?:sig|signature|token|expires|expiry|se|sp|sv|sr|st|skoid|sktid|skt|ske|sks|skv|ts|timestamp|x-amz-.+|x-goog-.+)$/i.test(name))url.searchParams.delete(name);
     url.hash='';url.searchParams.sort();return url.href;
   }catch{return src;}
 }
 const previewAssets=()=>previews().map(previewAsset).filter(Boolean);
 const idle=()=>!generatingControl()&&!snakeIndicator();
 const textHash=text=>{let h=2166136261;for(const c of norm(text)){h^=c.charCodeAt(0);h=Math.imul(h,16777619);}return (h>>>0).toString(16);};
 function conversation(){
   const users=qs('[data-message-author-role="user"]');const last=users.at(-1);
   const text=norm(last?.innerText||last?.textContent||'');
   return {count:users.length,lastId:last?.getAttribute('data-message-id')||last?.closest('[data-message-id]')?.getAttribute('data-message-id')||last?.closest('article')?.getAttribute('data-testid')||'',hash:textHash(text),text};
 }
 const evidence=c=>({count:c.count,lastId:c.lastId,hash:c.hash});
 const sameConversation=(a,b)=>a.hash===b.hash&&(a.lastId&&b.lastId?a.lastId===b.lastId:a.count===b.count);
 function promptInConversation(p,c){
   return !!c.text&&c.text===norm(p.prompt);
 }
 function freshOutput(p){return fingerprint().some(item=>!(p.baseline||[]).includes(item));}
 function newOutputEvidence(p){
   if(!freshOutput(p))return false;
   if(!p.assistantBaseline)return true;
   const known=p.assistantBaseline.keys||[],messages=assistantMessages();
   const lastKnown=messages.keys.indexOf(p.assistantBaseline.lastId);
   return previews().some(button=>{
     const img=button.querySelector('img');
     const key=[(img?.currentSrc||img?.src||'').slice(-160),button.getAttribute('aria-label')].join('|');
     if((p.baseline||[]).includes(key))return false;
     const owner=previewOwner(button);
     if(!owner)return !(p.previewAssets||[]).includes(previewAsset(button));
     if(known.includes(owner))return false;
     // Older messages being mounted above the prior last assistant are history,
     // while a new last message/unknown image still requires inspection.
     const at=messages.keys.indexOf(owner);
     return !(lastKnown>=0&&at>=0&&at<lastKnown);
   });
 }
 function previousFrameVisible(s,c){
   const line=s.prompts?.[(s.index||0)-1]||'',current=s.prompts?.[s.index||0]||'';
   const label=line.includes('||')?line.split('||')[0].trim():'';
   const currentLabel=current.includes('||')?current.split('||')[0].trim():'';
   return !!label&&c.text.includes(norm('Frame: '+label))&&(!currentLabel||!c.text.includes(norm('Frame: '+currentLabel)));
 }
 async function recoverPrepared(s,p,e,now){
   const c=conversation(),baseline=p.userBaseline;
   const messageSeen=promptInConversation(p,c);
   if(baseline&&!sameConversation(baseline,evidence(c))&&!messageSeen){await pause('A different message appeared while this frame was prepared. Inspect the conversation before resuming; no duplicate was submitted.');return;}
   if(messageSeen||(!value(e)&&!idle())){
     await put({pending:{...p,state:'waiting',clickedAt:now,editorEmptied:true,sawBusy:!idle(),sawNewPreview:newOutputEvidence(p),restoreSince:0},error:'',activity:'Prompt submission observed; waiting for this frame without sending again.'});return;
   }
   if(value(e)){
     await pause('Composer contains different text. Your draft was kept. Clear it and Resume only if this frame was not sent.');return;
   }
   if(!p.assistantBaseline&&freshOutput(p)&&!p.clickedAt&&previousFrameVisible(s,c)){
     const known=assistantMessages();
     if(known.lastId&&previews().every(button=>known.keys.includes(previewOwner(button)))){
       await put({pending:{...p,assistantBaseline:known,userBaseline:baseline||evidence(c),restoreSince:0,sendReadyAt:0},error:'',activity:'Recognized the previous frame after page refresh. Checking the empty composer before restoring.'});return;
     }
   }
   if(p.clickedAt){await pause('Send was already attempted for this frame. Inspect the conversation before using Retry; the prompt was not sent again.');return;}
   if(newOutputEvidence(p)){await pause('A new or unrecognized image appeared. Check whether this frame already generated before using Retry; the prompt was not sent again.');return;}
   // Existing v18 pending frames have no user-message baseline. Require a
   // visible conversation and a stable observation window before restoring.
   if(!baseline&&!c.count){await pause('Cannot verify the conversation before restoring this prompt. Inspect this frame and use Retry only if it was not sent.');return;}
   if((p.restoreCount||0)>=MAX_RESTORES){await pause('ChatGPT cleared this prompt repeatedly after 3 restore attempts. Refresh this ChatGPT tab, then inspect the frame before using Retry.');return;}
   if(!p.restoreSince){
     await put({pending:{...p,userBaseline:baseline||evidence(c),restoreSince:now,sendReadyAt:0},error:'',activity:`Row ${(s.index||0)+1}: composer cleared; checking before restoring the prompt.`});return;
   }
   if(now-p.restoreSince<RESTORE_DELAY)return;
   const latest=await get();
   if(latest.phase!=='running'||latest.queueId!==s.queueId||latest.index!==s.index||latest.pending?.state!=='prepared'||latest.pending?.prompt!==p.prompt)return;
   const current=edit(),check=conversation();
   if(!current||value(current)||!idle()||newOutputEvidence(p)||!sameConversation(p.userBaseline,evidence(check)))return;
   const restored={...p,baseline:fingerprint(),previewAssets:previewAssets(),assistantBaseline:assistantMessages(),restoreCount:(p.restoreCount||0)+1,restoreSince:0,sendReadyAt:0};
   // Persist the retry budget before touching the editor; never reset Send evidence.
   await put({pending:restored,error:'',activity:`Row ${(s.index||0)+1}: restoring cleared prompt (${restored.restoreCount}/${MAX_RESTORES}).`});
   const live=await get();
   if(live.phase!=='running'||live.queueId!==s.queueId||live.index!==s.index||live.pending?.state!=='prepared')return;
   const editor=edit();
   if(!editor||value(editor)||!idle()||!sameConversation(p.userBaseline,evidence(conversation()))||newOutputEvidence(restored))return;
   insert(editor,p.prompt);
   if(same(editor,p.prompt)){
     await saveHistory(s.index||0,s.prompts?.[s.index||0]?.split('||')[0],'in progress','Missing unsent prompt restored automatically');
     await put({activity:`Row ${(s.index||0)+1}: prompt restored automatically; checking Send before continuing.`});
   }
 }
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
 async function saveHistory(index,label,status,note=''){
   const s=await chrome.storage.local.get(['frameHistory','queueId']);
   const history=(s.frameHistory||[]).filter(x=>!(x.queueId===s.queueId&&x.index===index));
   history.push({queueId:s.queueId,index,label:String(label||`Row ${index+1}`).slice(0,80),status,at:new Date().toISOString(),note:String(note).slice(0,180)});
   await put({frameHistory:history.slice(-250)});
 }
 async function maybeDownload(p,index,line){
   const s=await chrome.storage.local.get('autoDownload');if(!s.autoDownload)return 'Auto-download off';
   const now=previews();
   const candidate=now.find(b=>{
     const im=b.querySelector('img');return im&&im.complete&&im.naturalWidth>0&&!p.baseline.includes([(im.currentSrc||im.src||'').slice(-160),b.getAttribute('aria-label')].join('|'));
   });
   if(!candidate)return 'Download skipped: unique new image not identifiable';
   const img=candidate.querySelector('img');
   try{
     const url=img.currentSrc||img.src;
     const res=await fetch(url);if(!res.ok)throw Error('Image fetch failed');
     const blob=await res.blob();if(!blob.type.startsWith('image/'))throw Error('Unexpected media');
     if(blob.size>16_000_000)throw Error('Image too large to download safely');
     const dataUrl=await new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result);r.onerror=reject;r.readAsDataURL(blob)});
     const label=(line.includes('||')?line.split('||')[0]:`Row_${index+1}`).trim();
     const fileName=`${String(index+1).padStart(3,'0')}_${label}`;
     const response=await chrome.runtime.sendMessage({action:'SAVE_FRAME_IMAGE',fileName,dataUrl});
     if(!response?.ok)throw Error(response?.error||'Download failed');
     return 'Downloaded';
   }catch(e){return `Download unavailable: ${e.message||e}`;}
 }
 function stop(){if(ticker)clearInterval(ticker);ticker=null;}
 async function pause(reason){stop();const x=await get();if(x.pending)await saveHistory(x.index||0,x.prompts?.[x.index||0]?.split('||')[0],'needs review',reason);await put({phase:'paused',error:reason,activity:'Paused safely; inspect this frame before continuing.'});}
 async function tick(){
  if(busy||positioning)return;busy=true;
  try{
   const s=await get();if(s.phase!=='running')return;
   const list=s.prompts||[],i=s.index||0;
   if(i>=list.length){stop();await put({phase:'done',pending:null,activity:'All imported frames completed.',error:''});return;}
   if(s.ownerTabId!=null){const owner=await chrome.runtime.sendMessage({action:'MY_TAB_ID'});if(owner?.tabId!==s.ownerTabId)return;}
   const now=Date.now();let p=s.pending;
   const e=edit();if(!e){
     if(p?.state==='prepared'&&!p.clickedAt){
       if(!p.composerMissingSince){await put({pending:{...p,composerMissingSince:now,sendReadyAt:0},activity:'ChatGPT is rebuilding the composer. Waiting before restoring the prompt.'});return;}
       if(now-p.composerMissingSince<COMPOSER_WAIT)return;
     }
     await pause('Composer not found. Refresh ChatGPT, then Resume this frame.');return;
   }
   if(p?.composerMissingSince){p={...p,composerMissingSince:0,sendReadyAt:0};await put({pending:p});}
   if(!p){
     if(!idle()){await put({activity:'Existing generation detected. Waiting before preparing another prompt.'});return;}
     if(value(e)){await pause('Unsent text exists in composer. Clear manually only after checking it.');return;}
     p={queueId:s.queueId,state:'prepared',prompt:build(list[i],s.master||''),baseline:fingerprint(),baselineHadPreview:previews().length>0,
        preparedAt:now,sendReadyAt:0,clickedAt:0,editorEmptied:false,sawBusy:false,sawPreviewDisappear:false,sawPreviewReturn:false,
        sawNewPreview:false,completeSince:0,userBaseline:evidence(conversation()),assistantBaseline:assistantMessages(),previewAssets:previewAssets(),restoreSince:0,restoreCount:0};
     await put({pending:p,error:'',activity:`Row ${i+1}: pasting prompt.`});
     insert(e,p.prompt);
     if(!same(e,p.prompt)){await put({activity:'ChatGPT changed the composer while pasting. Checking the unsent prompt before restoring.'});return;}
     await put({activity:`Row ${i+1}: pasted; awaiting enabled Send button.`});return;
   }
   if(p.queueId!==s.queueId){await pause('Queue was replaced during a pending frame.');return;}
   if(p.state==='prepared'){
     if(!same(e,p.prompt)){
       await recoverPrepared(s,p,e,now);return;
     }
     if(p.restoreSince){p={...p,restoreSince:0,sendReadyAt:0};await put({pending:p});}
     const b=sendButton();
     if(!b){if(p.sendReadyAt)await put({pending:{...p,sendReadyAt:0}});
       await put({activity:'Prompt ready; waiting for aria=Send submit button. Not clicking voice/stop.'});return;}
     if(!p.sendReadyAt){await put({pending:{...p,sendReadyAt:now},activity:'Enabled Send detected; stabilizing.'});return;}
     if(now-p.sendReadyAt<READY_MS)return;
     const b2=sendButton();if(!b2)return;
     const live=await get();
     if(live.phase!=='running'||live.queueId!==s.queueId||live.index!==s.index||live.pending?.state!=='prepared'||!same(edit(),p.prompt)||!idle())return;
     // Save first: a transient exception must NEVER cause a second click.
     p={...p,state:'waiting',clickedAt:now,editorEmptied:false};
     await put({pending:p,activity:`Row ${i+1}: clicked verified Send button once; awaiting generation lifecycle.`});
     const sending=await get();
     if(sending.phase!=='running'||sending.queueId!==s.queueId||sending.index!==s.index)return;
     const finalButton=sendButton();if(finalButton&&same(edit(),p.prompt))finalButton.click();return;
   }
   if(p.state!=='waiting'){await pause('Unknown state.');return;}
   const submittedTextGone=!same(e,p.prompt) && !value(e);
   const isBusy=generatingControl()||snakeIndicator();
   let changed=false;
   const update={...p};
   if(submittedTextGone&&!p.editorEmptied){update.editorEmptied=true;changed=true;}
   if(isBusy&&!p.sawBusy){update.sawBusy=true;changed=true;}
   // Diagnostic evidence: existing preview disappears during image creation and reappears at completion.
   if(p.baselineHadPreview&&previews().length===0&&!p.sawPreviewDisappear){update.sawPreviewDisappear=true;changed=true;}
   if(p.sawPreviewDisappear&&previews().length>0&&!p.sawPreviewReturn){update.sawPreviewReturn=true;changed=true;}
   if(newOutputEvidence(p)&&!p.sawNewPreview){update.sawNewPreview=true;changed=true;}
   const confirmsSubmission=update.editorEmptied&&(update.sawBusy||update.sawPreviewDisappear||update.sawNewPreview);
   const confirmsOutput=update.sawPreviewReturn||update.sawNewPreview;
   // Image output must be present, generator idle, and submission observed. Never count page-wide images.
   const complete=confirmsSubmission&&confirmsOutput&&previews().length>0&&idle()&&now-p.clickedAt>=3500;
   if(complete){
     if(!p.completeSince){update.completeSince=now;changed=true;}
     if(now-(update.completeSince||now)>=FINISH_MS){const result=await maybeDownload(p,i,list[i]);await saveHistory(i,list[i].split('||')[0],'completed',result);await put({index:i+1,pending:null,error:'',activity:`Completed row ${i+1}; ${result}. Proceeding to next imported row.`});return;}
   }else if(p.completeSince){update.completeSince=0;changed=true;}
   if(changed)await put({pending:update});
   await put({activity:`Row ${i+1} | editor cleared=${update.editorEmptied} | busy observed=${update.sawBusy} | preview disappeared=${update.sawPreviewDisappear} | preview returned=${update.sawPreviewReturn} | new preview=${update.sawNewPreview} | current previews=${previews().length} | idle=${idle()}.`});
   if(now-p.clickedAt>UNCERTAIN_MS && !update.editorEmptied && same(e,p.prompt)){await pause('Send clicked but prompt remains in editor. Check whether submission failed; no automatic retry.');return;}
   if(now-p.clickedAt>MAX_WAIT){await pause('Output not confirmed after 18 minutes. If image is complete, use Mark frame complete.');return;}
  }catch(err){await pause(`Unexpected queue error: ${err?.message||err}`);}finally{busy=false;}
 }
 function start(){stop();ticker=setInterval(tick,TICK);tick();}
 chrome.runtime.onMessage.addListener((msg,_sender,respond)=>{
  (async()=>{const s=await get();if(positioning)throw Error('Frame selection is being updated. Please wait.');switch(msg.action){
   case 'SELECT_FRAME':{
     if(busy||s.phase==='running')throw Error('Pause the queue before choosing a frame.');
     const row=Number(msg.row),list=s.prompts||[];
     if(!Number.isInteger(row)||row<1||row>list.length)throw Error(`Choose a frame position from 1 to ${list.length}.`);
     if(msg.queueId!==s.queueId)throw Error('The storyboard changed. Reopen the popup and choose the frame again.');
     if(s.pending&&s.ownerTabId!=null&&s.ownerTabId!==msg.tabId)throw Error('The pending frame belongs to another ChatGPT tab. Open that tab first.');
     if(!idle())throw Error('ChatGPT is still generating. Wait for it to finish before choosing a frame.');
     const editor=edit();if(!editor)throw Error('Open ChatGPT and wait for its message composer, then try again.');
     if(value(editor)&&!(s.pending&&same(editor,s.pending.prompt)))throw Error('Your composer has a different draft. It was kept. Clear it before changing frames.');
     positioning=true;
     try{
       const latest=await get();
       if(latest.phase==='running'||latest.queueId!==s.queueId||latest.index!==s.index||!idle())throw Error('Queue state changed. Pause and choose the frame again.');
       const current=edit();if(!current)throw Error('ChatGPT composer changed. Try again.');
       if(value(current)&&!(s.pending&&same(current,s.pending.prompt)))throw Error('Your composer draft changed. It was kept.');
       stop();
       if(value(current))insert(current,'');
       await put({index:row-1,pending:null,phase:'paused',ownerTabId:msg.tabId,error:'',activity:`Frame position ${row} selected. Start or Resume to continue. Existing files and history were kept.`});
     }finally{positioning=false;}
     break;
   }
   case 'START':case 'RESUME':{
     if(!s.prompts?.length)throw Error('Import or save prompts first.');
     if(s.phase==='done')throw Error('Queue complete; import new file or Reset.');
     if(s.pending&&s.ownerTabId!=null&&s.ownerTabId!==msg.tabId)throw Error('Pending frame belongs to another ChatGPT tab.');
     await put({phase:'running',ownerTabId:msg.tabId,error:'',activity:s.pending?'Resuming observation; no duplicate click.':'Preparing next row.'});start();break;
   }
   case 'PAUSE':stop();await put({phase:'paused',activity:'Paused; pending frame preserved.'});break;
   case 'COMPLETE':if(!s.pending)throw Error('No pending frame.');stop();await saveHistory(s.index||0,(s.prompts||[])[s.index||0]?.split('||')[0],'completed','Manually verified; auto-download not attempted');await put({index:(s.index||0)+1,pending:null,phase:'paused',activity:'Manually confirmed complete. Resume for next row.',error:''});break;
   case 'RETRY':if(!s.pending)throw Error('No pending frame.');if(!idle())throw Error('Generation may still be active.');stop();await put({pending:null,phase:'paused',activity:'Retry armed, only after verifying frame not generated.'});break;
   case 'RESET':stop();await put({phase:'idle',index:0,pending:null,error:'',activity:'Reset to first imported row.'});break;
  }respond({ok:true});})().catch(e=>respond({ok:false,error:e.message}));return true;
 });
 get().then(s=>{if(s.phase==='running')start();});
})();

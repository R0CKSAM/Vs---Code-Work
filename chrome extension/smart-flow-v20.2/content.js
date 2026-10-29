/* v16: lifecycle observed in the user's diagnostic log. No message-count/image-count assumptions. */
(()=>{
 if(window.__storyboardV16)return;window.__storyboardV16=true;
 const TICK=700, READY_MS=900, FINISH_MS=2500, UNCERTAIN_MS=15000, MAX_WAIT=18*60*1000;
 let ticker=null,busy=false,positioning=false,composerMissingAt=0;
 const keys=['master','prompts','index','phase','pending','error','activity','ownerTabId','ownerConversation','queueId','frameHistory','autoDownload','queueMode','repeatLine','referenceSummary','referenceSession'];
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
 const messageId=e=>e?.getAttribute('data-message-id')||e?.closest('[data-message-id]')?.getAttribute('data-message-id')||e?.closest('article')?.getAttribute('data-testid')||'';
 const assistantIds=()=>qs('[data-message-author-role="assistant"]').map(messageId).filter(Boolean);
 function imageAsset(button){
   const img=button.querySelector('img'),src=img?.currentSrc||img?.src||'';if(!src)return '';
   try{const url=new URL(src,location.href);if(!/^https?:$/.test(url.protocol))return src;
     for(const key of [...url.searchParams.keys()])if(/^(?:sig|signature|token|expires|expiry|se|sp|sv|sr|st|skoid|sktid|skt|ske|sks|skv|ts|timestamp|x-amz-.+|x-goog-.+)$/i.test(key))url.searchParams.delete(key);
     url.hash='';url.searchParams.sort();return url.href;
   }catch{return src;}
 }
 function repeatImages(p){
   const known=p.repeatAssistants||[],current=assistantIds(),last=current.indexOf(known.at(-1));
   return previews().filter(button=>{
     const img=button.querySelector('img'),asset=imageAsset(button);
     if(!asset||!img?.complete||!img.naturalWidth||(p.repeatAssets||[]).includes(asset))return false;
     const owner=messageId(button.closest('[data-message-author-role="assistant"]')||button.closest('article')?.querySelector('[data-message-author-role="assistant"]'));
     if(known.includes(owner))return false;
     const at=current.indexOf(owner);return !(last>=0&&at>=0&&at<last);
   });
 }
 const userEvidence=()=>{const users=qs('[data-message-author-role="user"]'),last=users.at(-1);return {count:users.length,id:messageId(last),text:norm(last?.innerText||last?.textContent||'')};};
 const sameUser=(a,b)=>a&&b&&a.text===b.text&&(a.id&&b.id?a.id===b.id:a.count===b.count);
 const referencesRequired=s=>/REFERENCE SET REQUIRED:/.test(s.master||'');
 function checkReferences(s,tabId){
   const summary=s.referenceSummary,session=s.referenceSession;
   if(referencesRequired(s)&&!summary?.names?.length)throw Error('This workbook requires character images. Choose Use Aarohan references (5), attach them, then confirm the uploads before Start.');
   if(!summary?.names?.length)return;
   if(referencesRequired(s)&&['Anaya','Arjun','Mehak','Trisha','Veer'].some(name=>!summary.names.some(file=>file.toLowerCase().includes(name.toLowerCase()))))throw Error('This Aarohan workbook requires references for Anaya, Arjun, Mehak, Trisha and Veer. Load the full five-image set.');
   if(session?.revision!==summary.revision||session.tabId!==tabId||session.conversation!==location.pathname||!['ready','sent'].includes(session.state))throw Error('Attach the saved character references to this ChatGPT conversation, wait for all uploads, then confirm them in Smart Flow before Start.');
 }
 async function attachReferences(s,tabId){
   if(busy||positioning||s.phase==='running'||s.pending)throw Error('Finish or reset the pending frame before attaching references.');
   const e=edit();if(!e||!idle()||value(e))throw Error('Open an idle ChatGPT conversation with an empty message box before attaching references.');
   const {referenceImages:images}=await chrome.storage.local.get('referenceImages');
   if(!images?.length||!s.referenceSummary?.names?.length)throw Error('Load character reference images first.');
   const prior=s.referenceSession;
   if(prior?.revision===s.referenceSummary.revision&&prior.tabId===tabId&&prior.conversation===location.pathname)throw Error('References were already attached here. Check ChatGPT before confirming; no duplicate upload was requested. To replace them, clear and load your reference set again.');
   positioning=true;
   try{
     const dt=new DataTransfer();
     for(const image of images){
       if(!/^data:image\/(png|jpeg|webp);base64,/.test(image.dataUrl||''))throw Error('Invalid reference image. Choose your images again.');
       const blob=await(await fetch(image.dataUrl)).blob();dt.items.add(new File([blob],image.name,{type:blob.type}));
     }
     const live=await get();if(live.phase==='running'||live.pending||live.referenceSummary?.revision!==s.referenceSummary.revision||!idle()||edit()!==e||value(e))throw Error('The queue or composer changed. References were not uploaded.');
     const inputs=qs('input[type="file"]').filter(input=>!input.disabled&&(!input.accept||/image|\.png|\.jpg|\.jpeg|\.webp/i.test(input.accept))&&(images.length===1||input.multiple));
     const scope=editorScope(e),input=inputs.find(input=>scope?.contains(input))||inputs[0];
     const referenceSession={revision:s.referenceSummary.revision,tabId,conversation:location.pathname,state:'attached'};
     // A request is not proof that the site's upload completed. The employee
     // checks the attachments before an explicit confirmation permits Start.
     await put({referenceSession,error:'',activity:'Reference upload requested. Check all attachments in ChatGPT, wait for uploads to finish, then confirm them in Smart Flow.'});
     try{
       if(input){input.files=dt.files;input.dispatchEvent(new Event('change',{bubbles:true}));}
       else e.dispatchEvent(new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true}));
     }catch(err){await put({referenceSession:null});throw err;}
   }finally{positioning=false;}
 }
 async function recoverPrompt(s,p,e,now){
   const user=userEvidence(),changed=p.userBaseline&&!sameUser(p.userBaseline,user);
   if(changed&&user.text===norm(p.prompt)||!value(e)&&!idle()){
     await put({pending:{...p,state:'waiting',clickedAt:now,editorEmptied:true,sawBusy:!idle()},error:'',activity:'Observed prompt submission. Waiting for its image without sending again.'});return;
   }
   if(value(e)){await pause('Your composer contains different text. Your draft was kept. Inspect it before resuming.');return;}
   if(!p.userBaseline||changed||p.clickedAt||repeatImages(p).length){await pause('The conversation changed or submission is uncertain. Check whether this frame was sent before using Retry. No duplicate was submitted.');return;}
   if((p.restoreCount||0)>=3){await pause('ChatGPT cleared the prompt three times. Refresh the tab, check the conversation, then Resume.');return;}
   if(!p.restoreSince){await put({pending:{...p,restoreSince:now,sendReadyAt:0},activity:'Composer cleared before Send. Checking before restoring the unsent prompt.'});return;}
   if(now-p.restoreSince<1400)return;
   const live=await get(),editor=edit();
   if(live.phase!=='running'||live.queueId!==s.queueId||live.index!==s.index||live.pending?.state!=='prepared'||!editor||value(editor)||!idle()||!sameUser(p.userBaseline,userEvidence())||repeatImages(p).length)return;
   const restored={...p,restoreCount:(p.restoreCount||0)+1,restoreSince:0,sendReadyAt:0};
   await put({pending:restored,error:'',activity:'Restoring the unsent prompt; Send will be checked again.'});
   const check=await get();if(check.phase==='running'&&check.queueId===s.queueId&&check.index===s.index&&edit()&&!value(edit())&&idle()&&sameUser(p.userBaseline,userEvidence()))insert(edit(),p.prompt);
 }
 async function finishRepeat(s,p){
   const live=await get();
   if(live.phase!=='running'||live.queueId!==s.queueId||live.index!==s.index||live.pending?.downloadId!==p.downloadId)return;
   await saveHistory(s.index||0,s.prompts[s.index||0].split('||')[0],'completed','Image download completed');
   const latest=await get();if(latest.queueId!==s.queueId||latest.index!==s.index)return;
   await put({index:(s.index||0)+1,pending:null,error:'',activity:`${s.queueMode==='repeat'?'Repeat':'Frame'} ${(s.index||0)+1}: image saved. Preparing the next message.`});
 }
 async function observeDownload(s,p){
   const result=await chrome.runtime.sendMessage({action:'FRAME_DOWNLOAD_STATUS',id:p.downloadId,queueId:s.queueId});
   if(!result?.ok)throw Error(result?.error||'Could not check image download.');
   if(result.state==='complete'){await finishRepeat(s,p);return;}
   if(result.state==='interrupted'){await pause('Image download failed: '+(result.error||'interrupted')+'. Resume to retry saving this image; the message will not be sent again.');return;}
   if(Date.now()-(p.downloadStartedAt||Date.now())>120000){await pause('Image download is still pending. Check Chrome Downloads, then Resume to check it again.');return;}
   await put({activity:`${s.queueMode==='repeat'?'Repeat':'Frame'} ${(s.index||0)+1}: waiting for the image download to finish. The next message has not been sent.`});
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
 async function maybeDownload(p,index,line,required=false){
   const s=await get();if(!s.autoDownload){if(required)throw Error('Repeat mode requires automatic image downloads.');return 'Auto-download off';}
   const now=required||p.repeatAssets?repeatImages(p):previews();
   const candidate=now.find(b=>{
     const im=b.querySelector('img');return im&&im.complete&&im.naturalWidth>0&&!p.baseline.includes([(im.currentSrc||im.src||'').slice(-160),b.getAttribute('aria-label')].join('|'));
   });
   if(!candidate){if(required)throw Error('Cannot identify the new completed image. Nothing else was sent.');return 'Download skipped: unique new image not identifiable';}
   const img=candidate.querySelector('img');
   try{
     const url=img.currentSrc||img.src;
     const res=await fetch(url,{signal:AbortSignal.timeout(30000)});if(!res.ok)throw Error('Image fetch failed');
     const blob=await res.blob();if(!blob.type.startsWith('image/'))throw Error('Unexpected media');
     if(blob.size>16_000_000)throw Error('Image too large to download safely');
     const dataUrl=await new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result);r.onerror=reject;r.readAsDataURL(blob)});
     const label=(line.includes('||')?line.split('||')[0]:`Row_${index+1}`).trim();
     const fileName=`${String(index+1).padStart(3,'0')}_${label}`;
     const live=await get();if(required&&(live.queueId!==p.queueId||live.index!==index))throw Error('The queue changed before saving this image.');
     const response=await chrome.runtime.sendMessage({action:'SAVE_FRAME_IMAGE',fileName,dataUrl,...(required?{queueId:p.queueId}:{})});
     if(!response?.ok)throw Error(response?.error||'Download failed');
     if(required){if(!Number.isInteger(response.id))throw Error('Chrome did not return a download ID.');return response.id;}
     return 'Downloaded';
   }catch(e){if(required)throw Error(`Image could not be saved: ${e.message||e}. Resume to retry saving; no new message will be sent.`);return `Download unavailable: ${e.message||e}`;}
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
   if(s.ownerConversation&&s.ownerConversation!==location.pathname){
     const user=userEvidence(),p=s.pending;
     // A new chat receives /c/<id> when its first message is submitted.
     // Adopt only that transition, in the owning tab, with the exact observed
     // first message. Navigating to another existing chat remains blocked.
     if(s.ownerConversation==='/'&&/^\/c\/[^/]+$/.test(location.pathname)&&p?.state==='waiting'&&p.clickedAt&&p.userBaseline&&!sameUser(p.userBaseline,user)&&user.text===norm(p.prompt)){
       await put({ownerConversation:location.pathname,...(s.referenceSession?.conversation==='/'?{referenceSession:{...s.referenceSession,conversation:location.pathname,state:'sent'}}:{})});return;
     }
     await pause('The ChatGPT conversation changed. Return to the original conversation before resuming this frame.');return;
   }
   if(s.referenceSummary?.names?.length||referencesRequired(s)){const owner=await chrome.runtime.sendMessage({action:'MY_TAB_ID'});checkReferences(s,owner?.tabId);}
   if(s.pending?.state==='saving'){if(s.pending.queueId!==s.queueId){await pause('Queue was replaced during a pending image download.');return;}await observeDownload(s,s.pending);return;}
   const e=edit();if(!e){if(!composerMissingAt)composerMissingAt=Date.now();if(Date.now()-composerMissingAt<10000){await put({activity:'Waiting for the ChatGPT composer to finish loading…'});return;}await pause('Composer not found. Open a ChatGPT conversation, check sign-in, and refresh the page.');return;}composerMissingAt=0;
   const now=Date.now();let p=s.pending;
   if(!p){
     if(!idle()){await put({activity:'Existing generation detected. Waiting before preparing another prompt.'});return;}
     if(value(e)){await pause('Unsent text exists in composer. Clear manually only after checking it.');return;}
     p={queueId:s.queueId,state:'prepared',prompt:s.queueMode==='repeat'?s.repeatLine:build(list[i],s.master||''),baseline:fingerprint(),baselineHadPreview:previews().length>0,
        repeatAssets:previews().map(imageAsset).filter(Boolean),repeatAssistants:assistantIds(),userBaseline:userEvidence(),restoreCount:0,
        preparedAt:now,sendReadyAt:0,clickedAt:0,editorEmptied:false,sawBusy:false,sawPreviewDisappear:false,sawPreviewReturn:false,
        sawNewPreview:false,completeSince:0};
     if(s.referenceSession?.state==='ready'){
       p.referenceRevision=s.referenceSummary.revision;
       if(s.queueMode!=='repeat')p.prompt+='\n\nCHARACTER REFERENCE GUIDE: The attached files are identity references: '+s.referenceSummary.names.join('; ')+'. Match each named character to their own reference. Use only the cast visible in this frame. Follow the storyboard master art style; do not reproduce the reference-sheet layout or include all characters in every frame.';
     }
     await put({pending:p,error:'',activity:`Row ${i+1}: pasting prompt.`});
     const live=await get();if(live.phase!=='running'||live.queueId!==s.queueId||live.index!==s.index)return;
     insert(e,p.prompt);
     if(!same(e,p.prompt)){await recoverPrompt(s,p,e,now);return;}
     await put({activity:`Row ${i+1}: pasted; awaiting enabled Send button.`});return;
   }
   if(p.queueId!==s.queueId){await pause('Queue was replaced during a pending frame.');return;}
   if(p.state==='prepared'){
     if(!same(e,p.prompt)){
       await recoverPrompt(s,p,e,now);return;
     }
     const b=sendButton();
     if(!b){if(now-p.preparedAt>90000){await pause('The prompt is ready but ChatGPT has not enabled Send. Check your session, attachments or usage limit, then Resume.');return;}if(p.sendReadyAt)await put({pending:{...p,sendReadyAt:0}});
       await put({activity:'Prompt ready; waiting for aria=Send submit button. Not clicking voice/stop.'});return;}
     if(!p.sendReadyAt){await put({pending:{...p,sendReadyAt:now},activity:'Enabled Send detected; stabilizing.'});return;}
     if(now-p.sendReadyAt<READY_MS)return;
     const b2=sendButton();if(!b2)return;
     // Save first: a transient exception must NEVER cause a second click.
     p={...p,state:'waiting',clickedAt:now,editorEmptied:false};
     await put({pending:p,activity:`Row ${i+1}: clicked verified Send button once; awaiting generation lifecycle.`});
     const live=await get();if(live.phase!=='running'||live.queueId!==s.queueId||live.index!==s.index){if(live.queueId===s.queueId&&live.index===s.index)await put({pending:{...p,state:'prepared',clickedAt:0,sendReadyAt:0}});return;}
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
   if((p.repeatAssets?repeatImages(p).length>0:prev.some(x=>!p.baseline.includes(x)))&&!p.sawNewPreview){update.sawNewPreview=true;changed=true;}
   const confirmsSubmission=update.editorEmptied&&(update.sawBusy||update.sawPreviewDisappear||update.sawNewPreview);
   if(confirmsSubmission&&p.referenceRevision&&s.referenceSession?.state==='ready'&&s.referenceSession.revision===p.referenceRevision)await put({referenceSession:{...s.referenceSession,state:'sent'}});
   const confirmsOutput=p.repeatAssets?repeatImages(p).length>0:update.sawPreviewReturn||update.sawNewPreview;
   // Image output must be present, generator idle, and submission observed. Never count page-wide images.
   const complete=confirmsSubmission&&confirmsOutput&&previews().length>0&&idle()&&now-p.clickedAt>=3500;
   if(complete){
     if(!p.completeSince){update.completeSince=now;changed=true;}
     if(now-(update.completeSince||now)>=FINISH_MS){
       if(s.queueMode==='repeat'||s.autoDownload){
         const id=await maybeDownload(p,i,list[i],true),live=await get();
         if(live.queueId===s.queueId&&live.index===s.index)await put({pending:{...update,state:'saving',downloadId:id,downloadStartedAt:now},error:'',activity:`${s.queueMode==='repeat'?'Repeat':'Frame'} ${i+1}: download started. Waiting before sending the next message.`});
         return;
       }
       const result=await maybeDownload(p,i,list[i]);await saveHistory(i,list[i].split('||')[0],'completed',result);await put({index:i+1,pending:null,error:'',activity:`Completed row ${i+1}; ${result}. Proceeding to next imported row.`});return;
     }
   }else if(p.completeSince){update.completeSince=0;changed=true;}
   if(changed)await put({pending:update});
   await put({activity:`Row ${i+1} | editor cleared=${update.editorEmptied} | busy observed=${update.sawBusy} | preview disappeared=${update.sawPreviewDisappear} | preview returned=${update.sawPreviewReturn} | new preview=${update.sawNewPreview} | current previews=${previews().length} | idle=${idle()}.`});
   if(now-p.clickedAt>UNCERTAIN_MS && !update.editorEmptied && same(e,p.prompt)){await pause('Send clicked but prompt remains in editor. Check whether submission failed; no automatic retry.');return;}
   if(now-p.clickedAt>MAX_WAIT){await pause('Output not confirmed after 18 minutes. If image is complete, use Mark frame complete.');return;}
   if(s.queueMode==='repeat'&&now-p.clickedAt>UNCERTAIN_MS&&update.editorEmptied&&idle()&&!repeatImages(p).length){await pause('No new downloadable image appeared. Check whether ChatGPT replied with text or reached a limit. No further repeat message was sent.');return;}
  }catch(err){await pause(`Unexpected queue error: ${err?.message||err}`);}finally{busy=false;}
 }
 function start(){stop();ticker=setInterval(tick,TICK);tick();}
 chrome.runtime.onMessage.addListener((msg,_sender,respond)=>{
  (async()=>{const s=await get();switch(msg.action){
   case 'PING':respond({ok:true,version:chrome.runtime.getManifest().version,composerReady:!!edit(),generating:!idle()});return;
   case 'ATTACH_REFERENCES':await attachReferences(s,msg.tabId);break;
   case 'CONFIRM_REFERENCES':{
     if(busy||positioning||s.phase==='running'||s.pending||!edit()||!idle()||value(edit()))throw Error('Keep ChatGPT idle with an empty message box while confirming its attachments.');
     const session=s.referenceSession;
     if(!session||session.state!=='attached'||session.revision!==s.referenceSummary?.revision||session.tabId!==msg.tabId||session.conversation!==location.pathname)throw Error('Attach the references to this conversation first.');
     await put({referenceSession:{...session,state:'ready'},error:'',activity:'Character references confirmed. Start will send them with your first frame prompt.'});break;
   }
   case 'SELECT_FRAME':{
     if(busy||positioning||s.phase==='running')throw Error('Pause and wait for the current action to finish before changing frames.');
     if(!Number.isInteger(msg.row)||msg.row<1||msg.row>(s.prompts?.length||0))throw Error('Choose a valid imported frame position.');
     if(msg.queueId!==s.queueId)throw Error('The storyboard changed. Reopen the popup and select again.');
     if(s.pending&&s.ownerTabId!=null&&s.ownerTabId!==msg.tabId)throw Error('The pending frame belongs to another ChatGPT tab.');
     if(!idle())throw Error('An image is still generating. Wait before changing frames.');
     const e=edit();if(!e)throw Error('Open a ChatGPT conversation first.');
     if(value(e)&&(!s.pending||!same(e,s.pending.prompt)))throw Error('Unrelated text is in your composer. Your draft was kept.');
     positioning=true;try{
       const live=await get();if(live.phase==='running'||live.queueId!==s.queueId||live.index!==s.index||!idle())throw Error('The queue changed. Try again after it pauses.');
       const editor=edit();if(!editor||value(editor)&&(!s.pending||!same(editor,s.pending.prompt)))throw Error('Your composer changed. Your draft was kept.');
       stop();if(value(editor))insert(editor,'');
       await put({index:msg.row-1,pending:null,phase:'paused',ownerTabId:msg.tabId,error:'',activity:`Frame position ${msg.row} selected. Choose Start or Resume. Existing files and history are kept.`});
     }finally{positioning=false;}
     break;
   }
   case 'START':case 'RESUME':{
     if(positioning)throw Error('Wait for the reference upload request to finish.');
     if(!s.prompts?.length)throw Error('Import or save prompts first.');
     checkReferences(s,msg.tabId);
     if(s.phase==='done')throw Error('Queue complete; import new file or Reset.');
     if(s.pending&&s.ownerTabId!=null&&s.ownerTabId!==msg.tabId)throw Error('Pending frame belongs to another ChatGPT tab.');
     if(s.pending&&s.ownerConversation&&s.ownerConversation!==location.pathname)throw Error('The pending image belongs to the original ChatGPT conversation. Return to that conversation before resuming.');
     if(s.queueMode==='repeat'){
       if(typeof s.repeatLine!=='string'||!s.repeatLine.trim()||s.repeatLine.length>4000)throw Error('Prepare a nonempty repeat message first.');
       if(!s.autoDownload)throw Error('Automatic downloads must be enabled for repeat mode.');
     }
       if(s.pending?.state==='saving'){
         const result=await chrome.runtime.sendMessage({action:'FRAME_DOWNLOAD_STATUS',id:s.pending.downloadId,queueId:s.queueId});
         if(!result?.ok)throw Error(result?.error||'Could not check the pending image download.');
         if(result.state==='interrupted')await put({pending:{...s.pending,state:'waiting',downloadId:null,completeSince:Date.now()-FINISH_MS}});
         else if(result.state==='in_progress')await put({pending:{...s.pending,downloadStartedAt:Date.now()}});
       }
     await put({phase:'running',ownerTabId:msg.tabId,ownerConversation:location.pathname,error:'',activity:s.pending?'Resuming observation; no duplicate click.':'Preparing next row.'});start();break;
   }
   case 'PAUSE':stop();await put({phase:'paused',activity:'Paused; pending frame preserved.'});break;
   case 'COMPLETE':if(s.queueMode==='repeat'||s.pending?.state==='saving')throw Error('Use Resume to finish saving this image.');if(!s.pending)throw Error('No pending frame.');stop();await saveHistory(s.index||0,(s.prompts||[])[s.index||0]?.split('||')[0],'completed','Manually verified; auto-download not attempted');await put({index:(s.index||0)+1,pending:null,phase:'paused',activity:'Manually confirmed complete. Resume for next row.',error:''});break;
   case 'RETRY':if(s.pending?.state==='saving')throw Error('Use Resume to check or retry saving this image.');if(!s.pending)throw Error('No pending frame.');if(!idle())throw Error('Generation may still be active.');stop();await put({pending:null,phase:'paused',activity:'Retry armed, only after verifying frame not generated.'});break;
   case 'RESET':stop();await put({phase:'idle',index:0,pending:null,error:'',activity:'Reset to first imported row.'});break;
  }respond({ok:true});})().catch(e=>respond({ok:false,error:e.message}));return true;
 });
 get().then(s=>{if(s.phase==='running')start();});
})();

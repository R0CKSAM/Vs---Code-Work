/* Storyboard Auto Queue v13: composer-scoped 3-state controls. Auto-send every imported row. */
(()=>{
 if(window.__storyboardQueueV13)return; window.__storyboardQueueV13=true;
 const MS=900, SETTLE=1800, DEADLINE=25*60*1000, SUBMIT_WINDOW=90000, ARROW_STABLE=1200;
 let timer=null,busy=false,epoch=0;
 const get=()=>chrome.storage.local.get(['master','prompts','index','phase','pending','error','activity','ownerTabId','queueId','manualDone','manualStartIndex']);
 const set=o=>chrome.storage.local.set(o);
 const sleep=ms=>new Promise(r=>setTimeout(r,ms));
 const all=(s,root=document)=>Array.from(root.querySelectorAll(s));
 const visible=e=>!!(e&&e.isConnected&&e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden');
 const users=()=>all('[data-message-author-role="user"]');
 const assistants=()=>all('[data-message-author-role="assistant"]');
 const stopNames=/stop (generating|streaming|response)|stop generating|stop-button|composer-stop-button/i;
 const active=()=>all('button').some(b=>visible(b)&&stopNames.test([b.dataset.testid,b.getAttribute('aria-label'),b.getAttribute('title')].join(' ')));
 const composer=()=>all('#prompt-textarea,[data-testid="prompt-textarea"],[contenteditable="true"][role="textbox"],textarea').find(visible);
 const text=e=>(e?.innerText||e?.value||'').trim();
 const signature=e=>{
   if(e.tagName==='IMG')return 'img:'+(e.currentSrc||e.src||'')+':'+e.naturalWidth;
   if(e.tagName==='VIDEO')return 'video:'+(e.currentSrc||e.src||'');
   if(e.tagName==='CANVAS')return 'canvas:'+e.width+'x'+e.height;
   return 'bg:'+getComputedStyle(e).backgroundImage;
 };
 const assets=root=>all('img,video,canvas,[style*="background-image"]',root).filter(visible).filter(e=>e.tagName!=='IMG'||(e.complete&&e.naturalWidth>=256)).map(signature);
 const messageId=e=>e?.closest('[data-message-id]')?.getAttribute('data-message-id')||e?.getAttribute('data-message-id')||'';
 const snapshot=()=>{
   const a=assistants(),u=users(),last=a.at(-1);
   return {userCount:u.length,assistantCount:a.length,lastAssistantId:messageId(last),lastAssistantText:text(last).slice(-200),assets:a.flatMap(assets),pageVisuals:assets(document.querySelector('main')||document.body),lastUserId:messageId(u.at(-1))};
 };
 const sceneSnippet=prompt=>{
   const m=prompt.match(/(?:^|\n)Scene:\s*([\s\S]*?)(?:\n\nGenerate exactly|$)/i);
   return (m?.[1]||prompt).replace(/\s+/g,' ').trim().slice(0,85);
 };
 const userSubmitted=p=>{
   const us=users(),old=p.base||{};
   if(us.length>old.userCount)return true;
   if(messageId(us.at(-1)) && messageId(us.at(-1))!==old.lastUserId)return true;
   const fragment=sceneSnippet(p.prompt).slice(0,45);
   return fragment.length>=16 && us.slice(-1).some(n=>text(n).replace(/\s+/g,' ').includes(fragment)) && (us.length>old.userCount || messageId(us.at(-1))!==old.lastUserId);
 };
 const delivered=p=>{
   const a=assistants(),last=a.at(-1);
   const old=p.base||{},now=last?assets(last):[];
   const pageNew=assets(document.querySelector('main')||document.body).filter(x=>!(old.pageVisuals||[]).includes(x));
   // Fallback for image UI that is mounted outside role-marked assistant message.
   if(assistantChanged(p)&&pageNew.some(x=>x.startsWith('img:')||x.startsWith('canvas:')) && !active())return true;
   if(!last||!now.length)return false;
   const isNewTurn=a.length>(old.assistantCount||0) || (!!messageId(last)&&messageId(last)!==old.lastAssistantId);
   const hasNewVisual=now.some(x=>!(old.assets||[]).includes(x));
   // Asset could be served with same URL across rerenders: a new assistant turn is mandatory.
   return isNewTurn && (hasNewVisual || now.some(x=>x.startsWith('img:')||x.startsWith('canvas:')));
 };
 const assistantChanged=p=>{
   const a=assistants(),last=a.at(-1),old=p.base||{};
   return a.length>(old.assistantCount||0) || (!!messageId(last)&&messageId(last)!==old.lastAssistantId);
 };
 // Three ChatGPT composer UI states: idle/voice, send-arrow, stop-square.
 // Never use generic buttons elsewhere on the page.
 const labels=b=>[b.getAttribute('aria-label'),b.getAttribute('title'),b.getAttribute('data-testid'),b.getAttribute('data-state')].filter(Boolean).join(' ').toLowerCase();
 const blocked=b=>/stop|voice|microphone|dictat|record|audio|attach|upload|tool|model|speech|cancel|search|plus/i.test(labels(b));
 const enabled=b=>visible(b)&&!b.disabled&&b.getAttribute('aria-disabled')!=='true'&&!blocked(b);
 function composerScope(e){
   if(!e)return null;
   let node=e;
   for(let i=0;i<7&&node;i++,node=node.parentElement){
     if(node.querySelectorAll('button').length>=2 && node.getBoundingClientRect().height<500)return node;
   }
   return e.closest('form')||e.parentElement;
 }
 function candidateArrow(){
   const e=composer();if(!e||!text(e)||active())return null;
   const scope=composerScope(e);if(!scope)return null;
   // Prefer reliable public attributes where available.
   const exact='button[data-testid="send-button"],button[data-testid="composer-send-button"],button[aria-label="Send prompt"],button[aria-label="Send message"],button[title="Send prompt"],button[type="submit"]';
   const explicit=all(exact,scope).filter(enabled);
   if(explicit.length===1)return explicit[0];
   if(explicit.length>1)return null;
   // Unlabeled up arrow: select the bottom-right visible SVG button scoped to composer.
   // Exclude all known microphone, voice, stop, attachment and model controls.
   const rect=e.getBoundingClientRect();
   const buttons=all('button',scope).filter(b=>enabled(b)&&b.querySelector('svg')&&b.getBoundingClientRect().width>=24);
   const possible=buttons.map(b=>({b,r:b.getBoundingClientRect()}))
     .filter(x=>x.r.left>rect.left+rect.width*.55 && x.r.top>=rect.top+rect.height*.35-25)
     .sort((x,y)=>y.r.right-x.r.right || y.r.bottom-x.r.bottom);
   if(!possible.length)return null;
   const best=possible[0];
   if(possible[1]&&Math.abs(best.r.right-possible[1].r.right)<10&&Math.abs(best.r.bottom-possible[1].r.bottom)<10)return null;
   // Do not confuse unlabeled voice button with Send; require send-looking SVG shape.
   const svg=best.b.querySelector('svg');
   const contents=(svg?.outerHTML||'').toLowerCase();
   const hasUpArrow=contents.includes('arrow-up')||contents.includes('lucide-arrow-up')||
     (!!svg?.querySelector('path') && /[mMlL]\s*[-0-9., ]+/.test(contents) && svg.querySelectorAll('path,line,polyline').length>=1);
   return hasUpArrow?best.b:null;
 }
 function controlState(){if(active())return 'STOP';if(candidateArrow())return 'SEND';return 'IDLE';}
 const isReady=()=>controlState()==='SEND';
 const button=()=>candidateArrow();
 const normalized=v=>(v||'').replace(/\s+/g,' ').trim();
 const composerHas=(e,p)=>normalized(text(e))===normalized(p);
 function insert(e,v){
   e.focus();
   if(e.tagName==='TEXTAREA'){
     const setter=Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value')?.set;
     setter?setter.call(e,v):e.value=v;
   }else{
     e.replaceChildren();
     const sel=window.getSelection(),range=document.createRange();range.selectNodeContents(e);range.collapse(true);sel.removeAllRanges();sel.addRange(range);
     if(!document.execCommand('insertText',false,v))e.textContent=v;
   }
   e.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:v}));
 }
 function build(line,master){const k=line.indexOf('||'),label=k>=0?line.slice(0,k).trim():'',scene=k>=0?line.slice(k+2).trim():line;
   return [master,label?`Frame: ${label}`:'',`Scene: ${scene}`,'Generate exactly ONE individual 16:9 image, not a contact sheet.'].filter(Boolean).join('\n\n');}
 function halt(){if(timer)clearInterval(timer);timer=null;epoch++;}
 async function pause(message){halt();await set({phase:'paused',error:message,activity:'Paused; check the ChatGPT conversation before taking action.'});}
 async function cycle(){
   if(busy)return;busy=true;
   try{
    const s=await get();if(s.phase!=='running')return;
    const idx=s.index||0,list=s.prompts||[];
    if(idx>=list.length){halt();await set({phase:'done',pending:null,activity:'All queue items finished.',error:''});return;}
    if(s.ownerTabId!==undefined&&s.ownerTabId!==null){
      // Only the tab that started the run is allowed to mutate the queue.
      const here=await new Promise(r=>chrome.runtime.sendMessage({action:'MY_TAB_ID'},r));
      if(here?.tabId!==s.ownerTabId)return;
    }
    if(s.pending){
      let p=s.pending;
      if(p.queueId!==s.queueId){await pause('Queue identity changed with pending frame.');return;}
      // Legacy recovery: v10 saved state='submitting' even after a completed image.
      if(p.state==='submitting' && !p.clickedAt){
        const e=composer();
        if(userSubmitted(p)||delivered(p)||assistantChanged(p)){
          p={...p,state:'waiting',clickedAt:p.sentAt||Date.now(),confirmedAt:Date.now(),stableSince:null};
          await set({pending:p,activity:'Legacy submission confirmed; monitoring output.'});return;
        }
        if(e&&composerHas(e,p.prompt)){
          p={...p,state:'prepared',readySince:null};
          await set({pending:p,activity:'Recovered pasted prompt; waiting for Send arrow.'});return;
        }
        await pause('Uncertain previous submission. Inspect ChatGPT; use Mark complete if image is finished.');return;
      }
      if(p.state==='prepared'){
        // Every row is auto-submitted after the previous image completes.
        const manual=false;
        const e=composer();
        if(!e){await pause('Composer disappeared. Refresh ChatGPT before resuming.');return;}
        if(!composerHas(e,p.prompt)){
          if(userSubmitted(p)||assistantChanged(p)||delivered(p)){
            await set({pending:{...p,state:'waiting',clickedAt:Date.now(),stableSince:null},manualDone:manual?true:s.manualDone,activity:'Observed submission; waiting for completed image.'});return;
          }
          await pause('Prepared prompt was changed or removed. Stopped to prevent sending the wrong text.');return;
        }
        if(!isReady()){
          if(p.readySince)await set({pending:{...p,readySince:null},activity:'Prompt pasted. Waiting for Stop square to become enabled Send arrow.'});
          else await set({activity:`Composer control: ${controlState()}. Waiting for SEND (up arrow); no click while STOP square/idle voice.`});
          return;
        }
        if(!p.readySince){await set({pending:{...p,readySince:Date.now()},activity:'Send arrow detected; waiting for stabilization.'});return;}
        if(Date.now()-p.readySince<ARROW_STABLE){await set({activity:'Send arrow stabilizing before submission.'});return;}
        if(!isReady())return;
        const b=button();if(!b)return;
        // Persist clicked state FIRST to avoid a second click after an unexpected reload.
        p={...p,state:'waiting',clickedAt:Date.now(),stableSince:null};
        await set({pending:p,activity:'Up arrow enabled: clicking Send once; verifying new message.'});
        b.click();return;
      }
      if(p.state==='waiting'){
        if(p.clickedAt && Date.now()-p.clickedAt>12000 && !userSubmitted(p) && !assistantChanged(p) && !delivered(p) && composerHas(composer(),p.prompt)){
          await pause('Click was attempted but prompt remains in composer. Check the Send arrow and click manually once, then Resume.');return;
        }
        if(delivered(p)&&!active()){
          if(!p.stableSince){await set({pending:{...p,stableSince:Date.now()},activity:`Frame ${idx+1}: image detected; waiting for stable completed response.`});return;}
          if(Date.now()-p.stableSince>=SETTLE){await set({index:idx+1,pending:null,error:'',activity:`Finished frame ${idx+1}; advancing in Excel row order.`});return;}
        }else{
          if(p.stableSince)await set({pending:{...p,stableSince:null}});
          await set({activity:`Frame ${idx+1}: submitted; waiting for new completed image.`});
        }
        if(Date.now()-(p.clickedAt||p.sentAt)>DEADLINE)await pause(`Frame ${idx+1} not confirmed after 25 minutes. Check image and mark complete manually if needed.`);
        return;
      }
      await pause('Unknown pending state. Inspect frame before retry.');return;
    }
    if(active()){await set({activity:'ChatGPT is generating another response; waiting before next row.'});return;}
    const e=composer();if(!e){await pause('ChatGPT composer not found. Refresh the tab and Resume.');return;}
    if(text(e)){await pause('ChatGPT composer contains unsent text. Clear it manually before Resume (nothing was sent).');return;}
    const prompt=build(list[idx],s.master||'');
    const p={queueId:s.queueId,base:snapshot(),prompt,state:'prepared',sentAt:Date.now(),clickedAt:null,readySince:null,stableSince:null};
    await set({pending:p,error:'',activity:`Frame ${idx+1}: preparing prompt (no submission yet).`});
    insert(e,prompt);
    if(!composerHas(e,prompt)) {await pause('Prompt could not be verified in composer. Nothing submitted.');return;}
    await set({activity:(!s.manualDone && idx===(s.manualStartIndex??idx)) ? `Row ${idx+1} pasted. CLICK SEND manually once; automatic sending begins after this image.` : `Row ${idx+1} pasted; waiting for enabled Send arrow.`});
   }catch(err){await pause('Queue error: '+(err?.message||String(err)))}finally{busy=false;}
 }
 function run(){halt();timer=setInterval(cycle,MS);cycle();}
 chrome.runtime.onMessage.addListener((msg,_sender,respond)=>{
  (async()=>{
    const s=await get();
    if(msg.action==='START'||msg.action==='RESUME'){
      if(!s.prompts?.length)throw Error('No saved queue.');
      if(s.phase==='done')throw Error('Queue is complete. Import a new file or Reset progress.');
      if(s.ownerTabId!=null && s.ownerTabId!==msg.tabId && s.pending)throw Error('A pending frame belongs to another ChatGPT tab. Return to that tab to resume or manually resolve it.');
      await set({phase:'running',ownerTabId:msg.tabId,manualStartIndex:s.manualStartIndex??(s.index||0),manualDone:true,error:'',activity:s.pending?'Resuming pending frame — not resending.':'Checking next row.'});run();
    }else if(msg.action==='PAUSE'){halt();await set({phase:'paused',activity:'Paused by user.'});}
    else if(msg.action==='COMPLETE'){
      if(!s.pending)throw Error('No pending frame.');
      halt();await set({index:(s.index||0)+1,pending:null,phase:'paused',activity:'Frame manually marked complete. Resume for next row.',error:''});
    }else if(msg.action==='RETRY'){
      if(!s.pending)throw Error('No pending frame.');
      if(active())throw Error('Generation still active; do not retry.');
      halt();await set({pending:null,phase:'paused',activity:'Retry armed; Resume will submit same frame.',error:'Only retry after confirming the frame was NOT generated.'});
    }else if(msg.action==='RESET'){halt();await set({phase:'idle',index:0,manualStartIndex:0,manualDone:false,pending:null,error:'',activity:'Reset to first imported row.'});}
    respond({ok:true});
  })().catch(e=>respond({ok:false,error:e.message}));return true;
 });
 // Do not forcibly pause on content script injection; only owner tab can work.
 get().then(s=>{if(s.phase==='running')run()});
})();

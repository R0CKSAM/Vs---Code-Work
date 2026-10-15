// Conservative DOM automation: it never advances solely because a timer passed.
// ChatGPT markup is not a stable API; update selectors when the site changes.
(() => {
  if (window.__storyboardQueueV2) return;
  window.__storyboardQueueV2 = true;
  const MIN_SETTLE_MS = 6500;
  const MAX_WAIT_MS = 7 * 60 * 1000;
  const MAX_SUBMIT_MS = 15000;
  let timer = null, busy = false;
  const sleep = ms => new Promise(r => setTimeout(r,ms));
  const get = async () => chrome.storage.local.get(['master','prompts','index','phase','pending','error','tabId']);
  const set = async o => chrome.storage.local.set(o);
  const all = sel => [...document.querySelectorAll(sel)];
  const visible = el => !!(el && el.isConnected && el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden');
  function editor(){return all('#prompt-textarea, [contenteditable="true"][data-testid="prompt-textarea"], div[contenteditable="true"][role="textbox"], textarea').find(visible)}
  function sendButton(){
    // Search the composer first. Never use an unlabelled SVG button: it may be voice, attach, etc.
    const candidates=all([
      'button[data-testid="send-button"]',
      'button[data-testid="composer-send-button"]',
      'button[data-testid*="send"]',
      'button[aria-label="Send prompt"]',
      'button[aria-label="Send message"]',
      'button[aria-label="Send"]',
      'button[title="Send prompt"]',
      'button[title="Send message"]',
      'button[title="Send"]',
      'form button[type="submit"]'
    ].join(','));
    const isSend=b=>{
      const words=[b.getAttribute('data-testid'),b.getAttribute('aria-label'),b.getAttribute('title')].filter(Boolean).join(' ').toLowerCase();
      return !/stop|voice|audio|microphone|cancel|dictat/.test(words) &&
        (/send|submit/.test(words) || (b.type==='submit' && !!b.closest('form')));
    };
    return candidates.find(b=>visible(b)&&isSend(b)&&!b.disabled&&b.getAttribute('aria-disabled')!=='true') || null;
  }
  async function waitSendButton(ms=8000){
    const start=Date.now();
    while(Date.now()-start<ms){
      const b=sendButton();if(b)return b;
      await sleep(250);
    }
    return null;
  }
  function submitViaForm(editorElement){
    const form=editorElement.closest('form');
    if(!form)return false;
    // requestSubmit dispatches the form's submit event, unlike form.submit().
    if(typeof form.requestSubmit!=='function')return false;
    const available=[...form.querySelectorAll('button[type="submit"],input[type="submit"]')]
      .filter(b=>visible(b)&&!b.disabled&&b.getAttribute('aria-disabled')!=='true');
    if(available.length===1)form.requestSubmit(available[0]);
    else form.requestSubmit();
    return true;
  }
  function stopVisible(){return all('button[data-testid="stop-button"], button[aria-label*="Stop generating"], button[aria-label*="Stop streaming"], button[aria-label="Stop"]').some(visible)}
  function assistantNodes(){return all('[data-message-author-role="assistant"]')}
  function imageKeys(){return assistantNodes().flatMap(n=>[...n.querySelectorAll('img')]).filter(visible).map(img=>img.currentSrc||img.src||img.getAttribute('alt')||'image')}
  // Only assess images inside assistant replies, not images in the composer or older user attachments.
  function snapshot(){return {assistants:assistantNodes().length,images:imageKeys()}}
  function hasNewImage(base){const now=snapshot();return now.images.length>base.images.length || now.images.some((s,i)=>!base.images.includes(s) && !!s)}
  function userCount(){return all('[data-message-author-role="user"]').length}
  function fill(el,value){el.focus();if(el.tagName==='TEXTAREA'){
    const setter=Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value')?.set;
    if(setter)setter.call(el,value);else el.value=value;
    el.dispatchEvent(new InputEvent('input',{bubbles:true,data:value,inputType:'insertText'}));
  }else{
    // insertText fires the input events handled by ProseMirror in many ChatGPT builds.
    document.getSelection()?.removeAllRanges();
    const range=document.createRange();range.selectNodeContents(el);range.collapse(false);
    const sel=window.getSelection();sel.removeAllRanges();sel.addRange(range);
    el.replaceChildren();document.execCommand('insertText',false,value);
    el.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:value}));
  }}
  function compose(line,master){const k=line.indexOf('||');const label=k>=0?line.slice(0,k).trim():'';const scene=k>=0?line.slice(k+2).trim():line;
    return [master,label?`Frame: ${label}`:'',`Scene: ${scene}`,'Generate exactly ONE new 16:9 image for this scene. Do not combine frames.'].filter(Boolean).join('\n\n')}
  async function fail(message){await set({phase:'paused',error:message});clearInterval(timer);timer=null}
  async function step(){if(busy)return;busy=true;try{
    const s=await get();if(s.phase!=='running')return;
    const prompts=s.prompts||[];
    if((s.index||0)>=prompts.length){await set({phase:'done',pending:null});clearInterval(timer);timer=null;return}
    if(s.pending){
      const p=s.pending,elapsed=Date.now()-p.sentAt;
      if(elapsed>MAX_WAIT_MS){await fail(`Frame ${s.index+1}: timeout waiting for completed image. Check the chat; resume to recheck, not resend.`);return}
      if(!hasNewImage(p.base)){return}
      // A new image must persist, and any active stop-generation control must disappear.
      if(stopVisible()){if(p.stableSince)await set({pending:{...p,stableSince:null}});return}
      if(!p.stableSince){await set({pending:{...p,stableSince:Date.now()}});return}
      if(Date.now()-p.stableSince<MIN_SETTLE_MS)return;
      await set({index:(s.index||0)+1,pending:null,error:''});return;
    }
    if(stopVisible())return;
    const e=editor();if(!e){await fail('Cannot locate the ChatGPT prompt editor.');return}
    const before=userCount(),base=snapshot();const prompt=compose(prompts[s.index||0],s.master||'');
    fill(e,prompt);await sleep(400);
    const btn=await waitSendButton();
    if(btn){btn.click();}
    else if(!submitViaForm(e)){
      await fail('No enabled Send button or compatible form found. The prompt remains pasted. Click Send manually, then check the chat before Resume.');return;
    }
    // Confirmation of user message prevents a failed click being counted as a submission.
    const started=Date.now();while(userCount()<=before && Date.now()-started<MAX_SUBMIT_MS){await sleep(400)}
    if(userCount()<=before){await fail('Could not confirm that ChatGPT received the prompt. Check chat before resuming.');return}
    await set({pending:{base,sentAt:Date.now(),stableSince:null},error:''});
  }catch(e){await fail('Automation paused: '+e.message)}finally{busy=false}}
  function run(){if(timer)clearInterval(timer);timer=setInterval(step,1700);step()}
  chrome.runtime.onMessage.addListener((msg)=>{
    (async()=>{
      if(msg.action==='START'){await set({phase:'running',index:0,pending:null,error:''});run()}
      if(msg.action==='PAUSE'){await set({phase:'paused'});clearInterval(timer);timer=null}
      if(msg.action==='RESUME'){const s=await get();if(!s.prompts?.length)return fail('No saved queue.');await set({phase:'running',error:''});run()}
      if(msg.action==='RESET'){await set({phase:'idle',index:0,pending:null,error:''});clearInterval(timer);timer=null}
    })().catch(console.error);
  });
  // Do not auto-resend after a reload: the status can be inspected and resumed manually.
  get().then(s=>{if(s.phase==='running')set({phase:'paused',error:'Tab reloaded or extension restarted. Review last frame and Resume.'})});
})();

(() => {
  if(window.__smartBannerGen) return; window.__smartBannerGen=true;
  const all=(s,r=document)=>[...r.querySelectorAll(s)];
  const visible=e=>!!e?.getClientRects().length;
  const editor=()=>all('#prompt-textarea,[contenteditable="true"][role="textbox"],textarea').find(visible);
  const text=e=>(e?.value??e?.innerText??'').trim();
  const scope=e=>e?.closest('form')||e?.closest('[data-testid="composer"]')||e?.parentElement?.parentElement?.parentElement;
  const idle=()=>!all('button').some(b=>visible(b)&&/^(stop|stop generating|stop response)$/i.test(b.getAttribute('aria-label')||'')||visible(b)&&/play snake while your image is generating/i.test(b.getAttribute('aria-label')||''));
  const roleSelector=role=>`[data-message-author-role="${role}"],[data-chatgpt-search-unit-key$=":${role}"]`;
  const users=()=>all(roleSelector('user'));
  const anchor=token=>users().find(e=>text(e).includes(`Smart Banner Gen job ${token}`));
  const wait=ms=>new Promise(r=>setTimeout(r,ms));
  let cancelled=false,working=false;
  function setText(e,s) {
    e.focus();
    if(e.tagName==='TEXTAREA') Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(e,s);
    else { e.replaceChildren(); const selection=getSelection(),range=document.createRange(); range.selectNodeContents(e); selection.removeAllRanges(); selection.addRange(range); if(!document.execCommand('insertText',false,s)) e.textContent=s; }
    e.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:s}));
  }
  function cleanComposer() {
    const e=editor(),s=scope(e);
    if(!e||!s) throw Error('ChatGPT composer not found. Sign in and reload this conversation.');
    if(!idle()) throw Error('ChatGPT is still generating. Wait for it to finish.');
    if(text(e)||all('img',s).length) throw Error('The composer contains a draft or attachment. Review and clear it before retrying.');
    return e;
  }
  async function run(m) {
    if(anchor(m.token)) return {submitted:true,path:location.pathname};
    if(working) throw Error('An upload is already in progress. Wait before retrying.');
    working=true;cancelled=false;
    try {
      const e=m.resumePrepared?editor():cleanComposer(),s=scope(e),startPath=location.pathname;
      if(m.resumePrepared){
        const norm=s=>(s||'').replace(/\s+/g,' ').trim(),images=all('img',s).filter(visible);
        if(!e||!idle())throw Error('The ChatGPT composer is not ready for draft recovery. Nothing was sent.');
        if(norm(text(e))!==norm(m.prompt))throw Error(`The saved draft text differs from this job (${norm(text(e)).length} vs ${norm(m.prompt).length} characters). Nothing was sent.`);
        if(images.length>1)throw Error('The pending draft has extra attachments. Nothing was sent.');
        if(images.length===0&&m.dataUrl){setText(e,'');m.resumePrepared=false;}
        else if(images.length!==1||!images[0].complete||!images[0].naturalWidth)throw Error('The pending attachment is not loaded. Nothing was sent.');
      }
      if(m.followup){
        if(m.path&&m.path!==startPath)throw Error('Return to the original thumbnail conversation before requesting its downloadable file.');
        if(!m.parentToken||anchor(m.parentToken)!==users().at(-1))throw Error('The previous thumbnail turn is no longer the latest user message. No follow-up was sent.');
      } else if(!m.resumePrepared) {
      const input=all('input[type="file"]').find(i=>!i.disabled&&(!i.accept||/image|\.png|\.jpg|\.webp/i.test(i.accept)));
      const blob=await(await fetch(m.dataUrl)).blob();
      const dt=new DataTransfer();dt.items.add(new File([blob],m.name,{type:blob.type}));
      if(input){input.files=dt.files;input.dispatchEvent(new Event('change',{bubbles:true}));}
      else e.dispatchEvent(new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer:dt}));
      const started=Date.now();let readySince=0;
      while(Date.now()-started<120000) {
        await wait(1000);
        if(cancelled) throw Error('Paused during upload. Review the composer; nothing further was sent.');
        if(location.pathname!==startPath||editor()!==e||text(e)||!idle()) throw Error('Conversation or composer changed during upload. Nothing further was sent.');
        const alert=all('[role="alert"],[data-state="error"]',s).find(a=>visible(a)&&/error|failed|unsupported|limit|too large/i.test(text(a)));
        if(alert) throw Error(`Attachment problem: ${text(alert).slice(0,240)}`);
        const images=all('img',s).filter(visible);
        const loading=all('[role="progressbar"],progress,[aria-busy="true"],[data-state="uploading"],.animate-spin',s).some(visible);
        if(images.length>1) throw Error('Unexpected extra attachment. Review the composer.');
        const ready=images.length===1&&images[0].complete&&images[0].naturalWidth&&!loading;
        if(!ready) readySince=0;
        else if(!readySince) readySince=Date.now();
        if(readySince&&Date.now()-readySince>=3000&&Date.now()-started>=10000) break;
      }
      if(!readySince||Date.now()-readySince<3000) throw Error('Upload could not be confirmed. Check ChatGPT before retrying.');
      }
      if(cancelled||location.pathname!==startPath||!m.resumePrepared&&text(e)) throw Error('Paused or composer changed. No prompt was sent.');
      if(!m.resumePrepared)setText(e,m.prompt);
      for(let i=0;i<30;i++) {
        await wait(500);
        if(cancelled) throw Error('Paused before sending. The draft was kept.');
        if(text(e).replace(/\s+/g,' ').trim()!==m.prompt.replace(/\s+/g,' ').trim()) throw Error('Prepared text changed. Inspect the draft before retrying.');
        const send=all('button[data-testid="send-button"],button[aria-label="Send"]',s).find(b=>visible(b)&&!b.disabled&&b.getAttribute('aria-disabled')!=='true');
        if(send){send.click();return {submitted:true,path:location.pathname};}
      }
      throw Error('Send did not become available. Inspect the prepared draft.');
    } finally {working=false;}
  }
  function poll(m) {
    if(m.path&&location.pathname!==m.path&&!anchor(m.token)) throw Error('Return to the queue’s ChatGPT conversation.');
    const user=anchor(m.token);
    if(!user) return {found:false,idle:idle(),working};
    if(users().at(-1)!==user) throw Error('Another message was sent after this job. Review the conversation before continuing.');
    const following=e=>!!(user.compareDocumentPosition(e)&Node.DOCUMENT_POSITION_FOLLOWING);
    const responses=all(roleSelector('assistant')).filter(following);
    const urls=[];
    for(const message of responses) {
      const container=message.closest('article')||message;
      const buttons=all('button[aria-label="Download file"]',container).filter(b=>!b.disabled);
      for(let i=0;i<buttons.length;i++)urls.push(`banner-file:${m.token}:${i}`);
      for(const a of all('a[href]',container)) if(/\/api\/library\/files\/[^/]+\/download|\/backend-api\/(?:files|estuary)|\.(?:png|jpe?g|webp)(?:\?|$)/i.test(a.href)) urls.push(a.href);
      for(const img of all('img',container)) if(img.complete&&img.naturalWidth>=256&&img.naturalHeight>=128) urls.push(img.currentSrc||img.src);
    }
    return {found:true,idle:idle(),path:location.pathname,urls:[...new Set(urls)],text:responses.map(text).join('\n').slice(-1500)};
  }
  async function asset(url) {
    if(url.startsWith('banner-file:')){
      const [,token,index]=url.split(':'),user=anchor(token);
      if(!user||users().at(-1)!==user)throw Error('The download no longer belongs to the current queue turn.');
      const responses=all(roleSelector('assistant')).filter(e=>user.compareDocumentPosition(e)&Node.DOCUMENT_POSITION_FOLLOWING);
      const buttons=responses.flatMap(e=>all('button[aria-label="Download file"]',e.closest('article')||e)).filter(b=>!b.disabled);
      const button=buttons[Number(index)];if(!button)throw Error('The expected downloadable file button disappeared.');
      let card=button.parentElement,preview=null;
      for(let i=0;i<8&&card&&!preview;i++,card=card.parentElement)preview=card.querySelector('button[aria-label^="Open preview of "]');
      const name=preview?.getAttribute('aria-label').replace(/^Open preview of /,'');
      if(!name)throw Error('Could not determine the downloadable image filename.');
      const pending=chrome.runtime.sendMessage({type:'BANNER_ARM_DOWNLOAD',name});
      await wait(300);button.click();const r=await pending;if(!r?.ok)throw Error(r?.error||'Download-file capture failed.');return r.dataUrl;
    }
    const parsed=new URL(url,location.href);
    if(!['https:','blob:','data:'].includes(parsed.protocol)) throw Error('Not an accessible image URL.');
    if(parsed.protocol==='https:'&&!/^(?:chatgpt\.com|chat\.openai\.com|(?:[a-z0-9-]+\.)*(?:oaiusercontent|oaistatic)\.com)$/.test(parsed.hostname)) throw Error('Image host is not approved.');
    const response=await fetch(parsed.href,{signal:AbortSignal.timeout(45000)});
    if(!response.ok) throw Error(`Download returned ${response.status}`);
    const blob=await response.blob();
    if(blob.size>30*1024*1024) throw Error('Output exceeds 30 MB.');
    return await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=reject;reader.readAsDataURL(blob);});
  }
  chrome.runtime.onMessage.addListener((m,s,reply)=>{
    if(s.id!==chrome.runtime.id||!['BANNER_RUN','BANNER_POLL','BANNER_ASSET','BANNER_CHECK','BANNER_CANCEL'].includes(m.type)) return;
    (async()=>{
      if(m.type==='BANNER_RUN') return run(m);
      if(m.type==='BANNER_POLL') return poll(m);
      if(m.type==='BANNER_ASSET') return {dataUrl:await asset(m.url)};
      if(m.type==='BANNER_CANCEL'){cancelled=true;return {};}
      return {version:'1.1.2',draftLength:text(editor()).length,attachments:editor()?all('img',scope(editor())).filter(visible).length:0,draftToken:/Smart Banner Gen job ([a-zA-Z0-9-]+)/.exec(text(editor()))?.[1]||'',ready:!!editor(),clean:!!editor()&&!text(editor())&&!all('img',scope(editor())).length,idle:idle(),working};
    })().then(result=>reply({ok:true,...result}),error=>reply({ok:false,error:error.message}));return true;
  });
})();

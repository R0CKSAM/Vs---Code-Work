(()=>{
 if(window.__storyboardDiagnosticsV1)return;
 window.__storyboardDiagnosticsV1=true;
 const KEY='sqd_v1_log',MAX=220;
 let recording=false,log=[],lastKey='',lastState=null,lastAt=0,observer=null,ticker=null,scheduled=false;
 const $=(q,r=document)=>[...r.querySelectorAll(q)];
 const vis=e=>!!(e&&e.isConnected&&e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden');
 const editor=()=>$('#prompt-textarea,[data-testid="prompt-textarea"],[contenteditable="true"][role="textbox"],textarea').find(vis);
 const info=e=>({tag:e.tagName.toLowerCase(),testid:(e.getAttribute('data-testid')||'').slice(0,90),aria:(e.getAttribute('aria-label')||'').slice(0,90),title:(e.getAttribute('title')||'').slice(0,90),type:(e.getAttribute('type')||'').slice(0,30),disabled:!!e.disabled||e.getAttribute('aria-disabled')==='true',svg:(e.querySelector('svg')?.getAttribute('class')||'').slice(0,90),paths:(e.querySelector('svg')?.querySelectorAll('path,line,polyline').length||0)});
 const snap=()=>{
  const ed=editor(), rect=ed?.getBoundingClientRect(), buttons=$('button').filter(vis);
  const nearby=buttons.filter(b=>{if(!rect)return false;let r=b.getBoundingClientRect();return r.bottom>rect.top-70&&r.top<rect.bottom+100&&r.right>rect.left-50&&r.left<rect.right+110;});
  const attrs=b=>[b.getAttribute('aria-label'),b.getAttribute('data-testid'),b.getAttribute('title')].filter(Boolean).join(' ');
  const stop=buttons.filter(b=>/stop generating|stop streaming|stop response|stop-button|composer-stop-button/i.test(attrs(b)));
  const turns=$('[data-message-author-role]');const users=turns.filter(t=>t.getAttribute('data-message-author-role')==='user');const bots=turns.filter(t=>t.getAttribute('data-message-author-role')==='assistant');
  const imgs=$('main img,main canvas,main video,[data-testid="conversation-turn"] img').filter(vis).filter(e=>{let r=e.getBoundingClientRect();return r.width>=140&&r.height>=100;});
  return {composer:!!ed,composerHasText:!!(ed&&(ed.innerText||ed.value||'').trim()),composerChars:(ed?.innerText||ed?.value||'').trim().length,composerTag:ed?.tagName||'',stopVisible:stop.length>0,nearbyButtons:nearby.map(info).slice(-12),userTurns:users.length,assistantTurns:bots.length,visualElements:imgs.length,conversationTurns:$('[data-testid="conversation-turn"]').length};
 };
 const stateKey=s=>JSON.stringify([s.composer,s.composerHasText,s.stopVisible,s.userTurns,s.assistantTurns,s.visualElements,s.conversationTurns,s.nearbyButtons]);
 async function add(kind,detail,force=false){
  if(!recording)return;
  let s=snap(),key=stateKey(s),now=Date.now();
  if(!force&&key===lastKey)return;
  lastKey=key;
  log.push({at:new Date(now).toISOString(),elapsedMs:lastAt?now-lastAt:0,kind,detail,...s});lastAt=now;
  if(log.length>MAX)log=log.slice(-MAX);
  try{await chrome.storage.local.set({[KEY]:log,sqd_v1_active:true});}catch{}
 }
 function check(reason){if(!recording||scheduled)return;scheduled=true;setTimeout(()=>{scheduled=false;add('state',reason);},120);}
 function start(){if(recording)return;recording=true;log=[];lastKey='';lastAt=0;chrome.storage.local.set({[KEY]:[],sqd_v1_active:true});add('start','User started read-only recording',true);
  observer=new MutationObserver(()=>check('DOM mutation'));observer.observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['disabled','aria-disabled','aria-label','data-testid','class','style']});
  ticker=setInterval(()=>check('poll'),500);
 }
 function stop(){if(!recording)return;add('stop','User ended recording',true);recording=false;observer?.disconnect();clearInterval(ticker);chrome.storage.local.set({sqd_v1_active:false,[KEY]:log});}
 chrome.runtime.onMessage.addListener((msg,sender,reply)=>{
  if(msg?.action==='DIAG_START'){start();reply({ok:true});}
  else if(msg?.action==='DIAG_STOP'){stop();reply({ok:true});}
  else if(msg?.action==='DIAG_SNAPSHOT'){add('snapshot','Manual snapshot',true);reply({ok:true,recording,events:log.length,snapshot:snap()});}
  else if(msg?.action==='DIAG_STATUS'){reply({ok:true,recording,events:log.length,snapshot:snap()});}
 });
 chrome.storage.local.get(['sqd_v1_active',KEY]).then(d=>{if(d.sqd_v1_active){start();add('restart','Tab was refreshed while recording',true);}}).catch(()=>{});
})();

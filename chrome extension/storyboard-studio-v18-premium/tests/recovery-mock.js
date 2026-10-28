window.TEST={data:{phase:'paused'},now:1000000,ticker:null,listener:null,clicks:0,checks:0,cases:[],errors:[],afterSet:null};
window.addEventListener('error',e=>TEST.errors.push(e.message));
window.addEventListener('unhandledrejection',e=>TEST.errors.push(String(e.reason)));
Date.now=()=>TEST.now;
window.setInterval=fn=>{TEST.ticker=fn;return 1;};
window.clearInterval=()=>{TEST.ticker=null;};
window.chrome={storage:{local:{get:async keys=>Object.fromEntries((Array.isArray(keys)?keys:[keys]).map(k=>[k,structuredClone(TEST.data[k])])),set:async patch=>{Object.assign(TEST.data,structuredClone(patch));if(TEST.afterSet)TEST.afterSet(patch);}}},runtime:{onMessage:{addListener:fn=>TEST.listener=fn},sendMessage:async msg=>{if(msg.action==='MY_TAB_ID')return {tabId:7};throw new Error('Unexpected runtime action '+msg.action);}}};
document.getElementById('composer').addEventListener('submit',event=>{
 event.preventDefault();TEST.clicks++;
 const editor=document.getElementById('prompt-textarea'),text=editor.value??editor.innerText;
 const user=document.createElement('div');user.dataset.messageAuthorRole='user';user.dataset.messageId='sent-'+TEST.clicks;user.textContent=text;document.getElementById('conversation').append(user);
 if(editor.tagName==='TEXTAREA')editor.value='';else editor.textContent='';
 document.getElementById('generation').innerHTML='<button aria-label="Stop generating">Stop</button>';
});
TEST.flush=async()=>{for(let i=0;i<30;i++)await Promise.resolve();await new Promise(resolve=>setTimeout(resolve,0));};
TEST.send=action=>new Promise(resolve=>TEST.listener({action,tabId:7},{},resolve));
TEST.step=async(ms=700)=>{TEST.now+=ms;if(TEST.ticker)await TEST.ticker();await TEST.flush();};
TEST.editor=()=>document.getElementById('prompt-textarea');
TEST.clear=()=>{const e=TEST.editor();if(e.tagName==='TEXTAREA')e.value='';else e.textContent='';};

window.TEST={now:1000000,data:{phase:'paused'},listener:null,ticker:null,clicks:0,sends:[],downloads:[],downloadStates:{},errors:[],nextId:1,failDownload:false,checks:0,cases:[],afterSet:null};
window.addEventListener('error',e=>TEST.errors.push(e.message));window.addEventListener('unhandledrejection',e=>TEST.errors.push(String(e.reason)));
Date.now=()=>TEST.now;window.setInterval=fn=>{TEST.ticker=fn;return 1;};window.clearInterval=()=>{TEST.ticker=null;};
window.chrome={storage:{local:{get:async keys=>Object.fromEntries((Array.isArray(keys)?keys:[keys]).map(k=>[k,structuredClone(TEST.data[k])])),set:async patch=>{Object.assign(TEST.data,structuredClone(patch));TEST.afterSet?.(patch);}}},runtime:{getManifest:()=>({version:'20.5.0'}),onMessage:{addListener:fn=>TEST.listener=fn},sendMessage:async msg=>{
 if(msg.action==='MY_TAB_ID')return {tabId:7};
 if(msg.action==='SAVE_FRAME_IMAGE'){if(TEST.failDownload)return {ok:false,error:'Synthetic disk failure'};const id=TEST.nextId++;TEST.downloads.push({...msg,id});TEST.downloadStates[id]={state:'in_progress'};return {ok:true,id};}
 if(msg.action==='FRAME_DOWNLOAD_STATUS')return {ok:true,...(TEST.downloadStates[msg.id]||{state:'interrupted',error:'missing'})};
 throw Error('Unexpected action '+msg.action);
}}};
TEST.editor=()=>document.getElementById('prompt-textarea');TEST.flush=async()=>{for(let i=0;i<30;i++)await Promise.resolve();await new Promise(r=>setTimeout(r,20));};
TEST.send=action=>new Promise(resolve=>TEST.listener({action,tabId:7},{},resolve));
TEST.step=async(ms=700)=>{TEST.now+=ms;if(TEST.ticker)await TEST.ticker();await TEST.flush();};
document.getElementById('composer').addEventListener('submit',e=>{
 e.preventDefault();TEST.clicks++;const editor=TEST.editor(),text=editor.value??editor.innerText;TEST.sends.push(text);
 const user=document.createElement('div');user.dataset.messageAuthorRole='user';user.dataset.messageId='user-'+TEST.clicks;user.textContent=text;document.getElementById('conversation').append(user);
 if(editor.tagName==='TEXTAREA')editor.value='';else editor.textContent='';document.getElementById('generation').innerHTML='<button aria-label="Stop generating">Stop</button>';
});
TEST.preview=async(asset,owner='assistant-'+asset)=>{
 const parent=document.createElement('div');parent.dataset.messageAuthorRole='assistant';parent.dataset.messageId=owner;
 const button=document.createElement('button');button.type='button';button.dataset.testid='generated-image-preview';button.setAttribute('aria-label','Generated image '+asset);
 const img=document.createElement('img');img.src='/pixel.png?asset='+encodeURIComponent(asset)+'&sig=one';button.append(img);parent.append(button);document.getElementById('conversation').append(parent);await img.decode();return {parent,button,img};
};
TEST.reset=async patch=>{
 if(TEST.listener)await TEST.send('PAUSE');await TEST.flush();TEST.now+=10000;TEST.clicks=0;TEST.sends=[];TEST.downloads=[];TEST.downloadStates={};TEST.nextId=1;TEST.failDownload=false;TEST.afterSet=null;
 TEST.data={master:'Must not be appended',prompts:['Repeat 001 || Next','Repeat 002 || Next'],repeatLine:'Next',queueMode:'repeat',index:0,phase:'paused',pending:null,queueId:'repeat-'+TEST.now,ownerTabId:7,frameHistory:[],autoDownload:true,...patch};
 document.getElementById('conversation').replaceChildren();document.getElementById('generation').replaceChildren();TEST.editor().value='';
};

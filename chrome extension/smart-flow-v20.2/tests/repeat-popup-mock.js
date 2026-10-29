window.POPUP_TEST={ready:null,interval:null,messages:[],answer:true,confirmations:[],errors:[]};
window.addEventListener('error',e=>POPUP_TEST.errors.push(e.message));window.addEventListener('unhandledrejection',e=>POPUP_TEST.errors.push(String(e.reason)));
const frame=document.createElement('iframe');frame.src='tests/repeat-chat.html';frame.style.cssText='position:fixed;left:-10000px;width:800px;height:600px';POPUP_TEST.ready=new Promise(r=>frame.onload=()=>r(frame.contentWindow.TEST));document.body.append(frame);
const store=async()=>{await POPUP_TEST.ready;return frame.contentWindow.chrome.storage.local;};
window.setInterval=fn=>{POPUP_TEST.interval=fn;return 1;};window.confirm=message=>{POPUP_TEST.confirmations.push(message);return POPUP_TEST.answer;};
window.chrome={runtime:{getManifest:()=>({version:'20.5.0'}),getURL:path=>path},storage:{local:{get:async keys=>(await store()).get(keys),set:async patch=>(await store()).set(patch)}},tabs:{query:async()=>[{id:7,url:'https://chatgpt.com/c/synthetic-repeat'}],sendMessage:async(id,msg)=>{POPUP_TEST.messages.push(msg);const test=await POPUP_TEST.ready;return new Promise(r=>test.listener(msg,{},r));}}};

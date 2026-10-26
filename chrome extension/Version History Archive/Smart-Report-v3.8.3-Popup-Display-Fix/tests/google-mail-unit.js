'use strict';
const fs=require('fs'),assert=require('assert'), crypto=require('crypto').webcrypto;
const src=fs.readFileSync(process.argv[2], 'utf8');
let mode='success'; const writes=[];let sends=0, lastMime='';
const chrome={runtime:{getManifest:()=>({oauth2:{client_id:'135438109521-b4ao4om1jdlv80g5i2a8shdfb169dusf.apps.googleusercontent.com'}})},identity:{getAuthToken:async()=>({token:'testtok'}),removeCachedAuthToken:async()=>{}}};
const fetch=async(url,opt)=>{
 if(url.includes('/userinfo'))return {ok:true,json:async()=>({email:'test@gmail.com',email_verified:true})};
 if(url.includes('/messages/send')){
  sends++;const raw=JSON.parse(opt.body).raw;
  lastMime=Buffer.from(raw.replace(/-/g,'+').replace(/_/g,'/'),'base64').toString('utf8');
  if(mode==='timeout') throw Error('Simulated timeout');
  if(mode==='403') return {ok:false,status:403,text:async()=>'{"error":"denied"}'};
  return {ok:true,status:200,json:async()=>({id:'confirmed-id'})};
 }
 throw Error('Unexpected fetch URL: '+url);
};
const put=async obj=>writes.push(structuredClone(obj));
const parseRecipients=(c,allow)=>{
 const groups={};for(const key of ['to','cc','bcc']){
  groups[key]=String(c[key]||'').split(/[,;\s]+/).filter(Boolean).map(address=>({emailAddress:{address}}));
  for(const v of groups[key])assert(allow.includes(v.emailAddress.address.split('@')[1]));
 }
 return groups;
};
const code=new Function('chrome','fetch','ALLOWED_DOMAINS','parseRecipients','put','crypto','TextEncoder','AbortSignal','btoa','console',src+'\nreturn {googleSendTest,googleProfile};');
const adapter=code(chrome,fetch,['vetostreaming.com','indiatvnews.com'],parseRecipients,put,crypto,TextEncoder,AbortSignal,btoa,console);
const c={to:'to@vetostreaming.com',cc:'cc@indiatvnews.com',bcc:'bcc@vetostreaming.com',dashboard:'https://grafana-apj.trafficpeak.live/d/demo/dash'};
const shot={mime:'image/png',data:'YmluYXJ5',ext:'png'};
global.checkUrl=x=>x;
(async()=>{
 const res=await adapter.googleSendTest(c,shot);
 assert(res.sender==='test@gmail.com'&&res.to===1&&res.cc===1&&res.bcc===1);
 assert(lastMime.includes('To: to@vetostreaming.com'));
 assert(lastMime.includes('Cc: cc@indiatvnews.com'));
 assert(lastMime.includes('Bcc: bcc@vetostreaming.com'));
 assert(writes.some(x=>x.gmailSubmissionPending&&x.gmailSubmissionPending.sender==='test@gmail.com'));
 assert(writes.at(-1).gmailSubmissionPending===null);
 mode='403';writes.length=0;
 await assert.rejects(()=>adapter.googleSendTest(c,shot),/HTTP 403/);
 assert(writes.at(-1).gmailSubmissionPending===null,'Definitive HTTP failure must release pending marker');
 mode='timeout';writes.length=0;
 await assert.rejects(()=>adapter.googleSendTest(c,shot),/acceptance is unconfirmed/);
 assert(writes.at(-1).gmailSubmissionPending&&writes.at(-1).gmailSubmissionPending.sender==='test@gmail.com','Uncertain Gmail failure must preserve marker');
 console.log('PASS Gmail mock acceptance, To/CC/BCC MIME, HTTP failure cleanup, network uncertainty guard; calls:',sends);
})().catch(e=>{console.error(e);process.exit(1)});

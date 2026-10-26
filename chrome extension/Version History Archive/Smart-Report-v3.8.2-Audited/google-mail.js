"use strict";
// Opt-in Google Gmail adapter. Requires an OAuth Chrome Extension client in manifest.json.
const GOOGLE_GMAIL_SCOPES = ['https://www.googleapis.com/auth/gmail.send','https://www.googleapis.com/auth/userinfo.email'];
function googleConfigured(){return /\d+-[a-zA-Z0-9_-]+\.apps\.googleusercontent\.com$/.test(chrome.runtime.getManifest().oauth2?.client_id||'');}
async function googleToken(interactive=false){
  if(!googleConfigured())throw Error('Google is not configured. Set up the Chrome Extension OAuth client ID in manifest.json (see GOOGLE-SETUP.md).');
  try{const result=await chrome.identity.getAuthToken({interactive,scopes:GOOGLE_GMAIL_SCOPES});const token=typeof result==='string'?result:result?.token;if(!token)throw Error('Google returned no token.');return token;}
  catch(e){throw Error('Google authorization needed: '+e.message);}
}
async function googleProfile(interactive=false){
  const token=await googleToken(interactive);
  const r=await fetch('https://www.googleapis.com/oauth2/v3/userinfo',{headers:{Authorization:'Bearer '+token},signal:AbortSignal.timeout(20000)});
  if(!r.ok){if(r.status===401)await chrome.identity.removeCachedAuthToken({token});throw Error('Google identity verification failed (HTTP '+r.status+').');}
  const j=await r.json();if(!j.email||j.email_verified!==true)throw Error('A verified Google email is required.');return {email:j.email,token};
}
function base64Utf8(s){const bytes=new TextEncoder().encode(s);let data='';for(let i=0;i<bytes.length;i+=8192)data+=String.fromCharCode(...bytes.slice(i,i+8192));return btoa(data);}
function rawGmailEmail({to,cc,bcc,subject,body,shot,name}){
  const addr=x=>x.map(e=>e.emailAddress.address).join(', ');
  const boundary='smartreport-'+crypto.randomUUID();
  const subjectHeader='=?UTF-8?B?'+base64Utf8(subject)+'?=';
  const h=['MIME-Version: 1.0','To: '+addr(to),...(cc.length?['Cc: '+addr(cc)]:[]),...(bcc.length?['Bcc: '+addr(bcc)]:[]),'Subject: '+subjectHeader,'Content-Type: multipart/mixed; boundary="'+boundary+'"'];
  const lines=[...h,'','--'+boundary,'Content-Type: text/plain; charset=UTF-8','Content-Transfer-Encoding: base64','',base64Utf8(body),'--'+boundary,'Content-Type: '+shot.mime+'; name="'+name+'"','Content-Disposition: attachment; filename="'+name+'"','Content-Transfer-Encoding: base64','',shot.data.match(/.{1,76}/g)?.join('\r\n')||'','--'+boundary+'--',''];
  const utf8=new TextEncoder().encode(lines.join('\r\n'));
  let binary='';for(let i=0;i<utf8.length;i+=8192)binary+=String.fromCharCode(...utf8.slice(i,i+8192));
  return btoa(binary).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
}
async function googleSendTest(c,shot){
  // The company recipient-domain rules continue to apply to Gmail submissions.
  const permitted=ALLOWED_DOMAINS;
  if(!permitted.length)throw Error('Company recipient domains must be configured before Gmail sends are enabled.');
  const parsed=parseRecipients(c,permitted);
  if(!parsed.to.length)throw Error('Enter at least one To recipient.');
  const {email:sender,token}=await googleProfile(false);
  const name='Grafana_Test_'+new Date().toISOString().replace(/[:.]/g,'-')+'.'+shot.ext;
  const raw=rawGmailEmail({...parsed,subject:'[TEST] Grafana Dashboard Report',body:'Smart Report Google Gmail test.\nSender: '+sender+'\nCaptured: '+new Date().toISOString()+'\nGrafana: '+checkUrl(c.dashboard),shot,name});
  await put({gmailSubmissionPending:{at:Date.now(),sender,recipients:parsed.to.length+parsed.cc.length+parsed.bcc.length}});
  let r;try{r=await fetch('https://gmail.googleapis.com/gmail/v1/users/me/messages/send',{method:'POST',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},body:JSON.stringify({raw}),signal:AbortSignal.timeout(30000)});}
  catch(e){throw Error('Gmail acceptance is unconfirmed (network/timeout). Check Gmail Sent Items before retrying to avoid duplicates. '+e.message);}
  if(!r.ok){await put({gmailSubmissionPending:null});if(r.status===401)await chrome.identity.removeCachedAuthToken({token});let reason=await r.text();throw Error('Gmail send failed (HTTP '+r.status+'): '+reason.slice(0,250));}
  let result;try{result=await r.json();}catch(e){throw Error('Gmail acceptance is unconfirmed (response parse). Check Gmail Sent Items before retrying. '+e.message);}
  await put({gmailSubmissionPending:null});return {sender,id:result.id,to:parsed.to.length,cc:parsed.cc.length,bcc:parsed.bcc.length};
}

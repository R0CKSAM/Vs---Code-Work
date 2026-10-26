'use strict';
const $=id=>document.getElementById(id);
const SCOPES='openid profile User.Read Mail.Send';
const redirect=chrome.identity.getRedirectURL('');
let screenshot=null, filename=null, capturing=false, sending=false;
const tell=(s)=>$('status').textContent=s;
const b64url=(buf)=>btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
const nonce=()=>b64url(crypto.getRandomValues(new Uint8Array(32)));
$('redirectbox').textContent='Registered redirect: '+redirect;
async function init(){const data=await chrome.storage.local.get(['client','tenant','recipient']);for(const k of ['client','tenant','recipient'])$(k).value=data[k]||'';}
init();
async function storeConfig(){let client=$('client').value.trim(),tenant=$('tenant').value.trim(),recipient=$('recipient').value.trim();await chrome.storage.local.set({client,tenant,recipient});return {client,tenant,recipient};}
function validateId(x){return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(x);}
function parseDataUrl(url){const found=/^data:image\/png;base64,([A-Za-z0-9+/=]+)$/.exec(url);if(!found)throw Error('Capture was not a PNG screenshot');return found[1];}
async function capture(){if(capturing)return;capturing=true;$('capture').disabled=true;try{
 const [tab]=await chrome.tabs.query({active:true,currentWindow:true});
 if(!tab||!tab.id||!/^https:\/\/grafana-apj\.trafficpeak\.live\//i.test(tab.url||''))throw Error('Please open and select your Grafana dashboard tab before clicking Capture.');
 tell('Capturing visible Grafana tab...');
 const data=await chrome.tabs.captureVisibleTab(tab.windowId,{format:'png'});parseDataUrl(data);
 screenshot=data;filename='Grafana_Report_'+new Date().toISOString().replace(/[:.]/g,'-')+'.png';$('preview').src=data;$('previewwrap').hidden=false;
 $('previewmeta').textContent=`${filename} • Visible browser area only`;tell('Screenshot captured. Review the preview, then enter the email recipient and click Send Test Email.');
 }catch(e){tell('Capture error: '+e.message)}finally{capturing=false;$('capture').disabled=false;}}
$('capture').addEventListener('click',capture);
$('save').addEventListener('click',()=>{if(!screenshot)return;const a=document.createElement('a');a.href=screenshot;a.download=filename||'Grafana_Report.png';a.click();});
async function signInAndGetToken(client,tenant){
 const verifier=nonce(),state=nonce(),digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(verifier));
 const authUrl=new URL(`https://login.microsoftonline.com/${tenant}/oauth2/v2.0/authorize`);
 authUrl.search=new URLSearchParams({client_id:client,response_type:'code',redirect_uri:redirect,response_mode:'query',scope:SCOPES,state,code_challenge:b64url(digest),code_challenge_method:'S256',prompt:'select_account'}).toString();
 tell('Opening Microsoft sign-in / consent...');
 const callback=await chrome.identity.launchWebAuthFlow({url:authUrl.href,interactive:true});
 if(!callback)throw Error('Microsoft did not return a sign-in response');
 const params=new URL(callback).searchParams;
 if(params.get('error'))throw Error(params.get('error_description')||params.get('error'));
 if(params.get('state')!==state)throw Error('OAuth state mismatch');
 const code=params.get('code');if(!code)throw Error('Microsoft returned no authorization code');
 const r=await fetch(`https://login.microsoftonline.com/${tenant}/oauth2/v2.0/token`,{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({client_id:client,grant_type:'authorization_code',code,redirect_uri:redirect,code_verifier:verifier,scope:SCOPES})});
 const json=await r.json();if(!r.ok)throw Error(json.error_description||json.error||'Token exchange failed');
 return json.access_token; // Kept in memory only; not written to local storage.
}
$('send').addEventListener('click',async()=>{if(sending)return;sending=true;$('send').disabled=true;try{
 if(!screenshot)throw Error('Capture and preview the Grafana screenshot first.');
 const {client,tenant,recipient}=await storeConfig();
 if(!validateId(client)||!validateId(tenant))throw Error('Enter the exact Entra Application (client) ID and Directory (tenant) ID.');
 if(!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(recipient))throw Error('Enter a valid recipient email address.');
 const subject=$('subject').value.trim()||'Grafana Dashboard Screenshot — Test';
 const token=await signInAndGetToken(client,tenant);
 tell('Sending exactly one email via Microsoft Graph...');
 const body={message:{subject,body:{contentType:'Text',content:'Smart Report test: attached is the visible Grafana dashboard screenshot. Captured at '+new Date().toLocaleString()+'.'},toRecipients:[{emailAddress:{address:recipient}}],attachments:[{'@odata.type':'#microsoft.graph.fileAttachment',name:filename,contentType:'image/png',contentBytes:parseDataUrl(screenshot)}]},saveToSentItems:true};
 const r=await fetch('https://graph.microsoft.com/v1.0/me/sendMail',{method:'POST',headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/json'},body:JSON.stringify(body)});
 if(!r.ok){let reason=await r.text();try{const j=JSON.parse(reason);reason=j.error?.message||reason}catch{}throw Error(`Microsoft Graph ${r.status}: ${reason.slice(0,400)}`)}
 tell(`Microsoft accepted the test email for delivery to ${recipient} (HTTP ${r.status}). Check Outlook Sent Items and the recipient inbox. No recurring schedule enabled.`);
 }catch(e){tell('Email test error: '+e.message)}finally{sending=false;$('send').disabled=false;}});

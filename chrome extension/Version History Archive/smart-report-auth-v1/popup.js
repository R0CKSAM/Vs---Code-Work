'use strict';
const $=id=>document.getElementById(id);
const scopes='openid profile offline_access User.Read Mail.Send';
let redirect=chrome.identity.getRedirectURL('');
$('redirect').value=redirect;
const status=(message)=>{$('status').textContent=message};
const b64url=(buf)=>btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
const random=()=>b64url(crypto.getRandomValues(new Uint8Array(32)));
$('copy').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(redirect);status('Redirect URL copied. Add it in Microsoft Entra first.')}catch(e){status('Copy failed: '+e.message)}});
async function init(){const {client='',tenant=''}=await chrome.storage.local.get(['client','tenant']);$('client').value=client;$('tenant').value=tenant;}
init();
$('signin').addEventListener('click',async()=>{
 const client=$('client').value.trim(),tenant=$('tenant').value.trim();
 if(!/^[0-9a-f-]{36}$/i.test(client)||!/^[0-9a-f-]{36}$/i.test(tenant)){status('Please enter valid Client ID and Tenant ID (GUID format).');return;}
 $('signin').disabled=true;
 try{
  await chrome.storage.local.set({client,tenant});
  const verifier=random(),state=random(),digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(verifier));
  const endpoint=`https://login.microsoftonline.com/${tenant}/oauth2/v2.0/authorize`;
  const p=new URLSearchParams({client_id:client,response_type:'code',redirect_uri:redirect,response_mode:'query',scope:scopes,state,code_challenge:b64url(digest),code_challenge_method:'S256',prompt:'select_account'});
  status('Opening Microsoft sign-in...');
  const callback=await chrome.identity.launchWebAuthFlow({url:`${endpoint}?${p}`,interactive:true});
  if(!callback)throw Error('No OAuth redirect received');
  const result=new URL(callback),err=result.searchParams.get('error');
  if(err)throw Error(`${err}: ${result.searchParams.get('error_description')||''}`);
  if(result.searchParams.get('state')!==state)throw Error('Security check failed (state mismatch)');
  const code=result.searchParams.get('code');if(!code)throw Error('No authorization code returned');
  status('Sign-in returned successfully. Testing Microsoft Graph...');
  const response=await fetch(`https://login.microsoftonline.com/${tenant}/oauth2/v2.0/token`,{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({client_id:client,grant_type:'authorization_code',code,redirect_uri:redirect,code_verifier:verifier,scope:scopes})});
  const auth=await response.json();if(!response.ok)throw Error(auth.error_description||auth.error||'Token request failed');
  const me=await fetch('https://graph.microsoft.com/v1.0/me?$select=displayName,mail,userPrincipalName',{headers:{Authorization:`Bearer ${auth.access_token}`}});
  const profile=await me.json();if(!me.ok)throw Error(profile.error?.message||'Graph user test failed');
  // Deliberately do not persist the access/refresh tokens in this diagnostic build.
  status(`Connected successfully as ${profile.displayName||'Microsoft 365 user'} (${profile.mail||profile.userPrincipalName||'email unavailable'}). No email sent. You can now proceed to the screenshot/email test build.`);
 }catch(e){status(`Sign-in test failed: ${e.message}`)}finally{$('signin').disabled=false;}
});
$('signout').addEventListener('click',async()=>{await chrome.storage.local.remove(['client','tenant']);$('client').value='';$('tenant').value='';status('Local configuration cleared. This build stores no tokens.');});

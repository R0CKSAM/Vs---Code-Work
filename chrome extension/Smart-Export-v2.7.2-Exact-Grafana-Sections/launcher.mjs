import {openWorkspace,returnToGrafana,rememberGrafanaTabIfActive} from './tab-nav.mjs';
const status=document.getElementById('launchStatus');
const version=document.querySelector('.version');if(version)version.textContent='v'+chrome.runtime.getManifest().version;
let navigating=false;
rememberGrafanaTabIfActive().catch(()=>{});
async function run(action,msg){if(navigating)return;navigating=true;for(const b of document.querySelectorAll('button'))b.disabled=true;status.textContent=msg;try{await action();window.close();}catch(e){status.textContent='Could not switch tabs: '+e.message;}finally{navigating=false;for(const b of document.querySelectorAll('button'))b.disabled=false;}}
document.getElementById('openWorkspace').addEventListener('click',()=>run(openWorkspace,'Opening your workspace…'));
document.getElementById('backGrafana').addEventListener('click',()=>run(returnToGrafana,'Finding your dashboard…'));

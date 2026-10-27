import {openWorkspace,returnToGrafana,rememberGrafanaTabIfActive} from './tab-nav.mjs';
const status=document.getElementById('launchStatus');
rememberGrafanaTabIfActive().catch(()=>{});
async function run(action,msg){status.textContent=msg;try{await action();window.close();}catch(e){status.textContent='Could not switch tabs: '+e.message;}}
document.getElementById('openWorkspace').addEventListener('click',()=>run(openWorkspace,'Opening your workspace…'));
document.getElementById('backGrafana').addEventListener('click',()=>run(returnToGrafana,'Finding your dashboard…'));

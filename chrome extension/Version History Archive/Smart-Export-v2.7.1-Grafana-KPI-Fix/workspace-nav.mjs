import {returnToGrafana} from './tab-nav.mjs';
const button=document.getElementById('openGrafana');
button?.addEventListener('click',async()=>{
 const label=button.textContent;button.disabled=true;button.textContent='Opening Grafana…';
 try{await returnToGrafana();}catch(e){button.textContent='Could not open Grafana';console.error(e);setTimeout(()=>button.textContent=label,3000);}finally{button.disabled=false;}
});

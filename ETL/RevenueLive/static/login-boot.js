'use strict';
(()=>{
  const root=document.documentElement,loading=document.getElementById('appLoading');
  const ready=new Promise(resolve=>window.addEventListener('revenuelive:ready',resolve,{once:true}));
  const loaded=document.readyState==='complete'?Promise.resolve():new Promise(resolve=>window.addEventListener('load',resolve,{once:true}));
  function failed(){loading.dataset.error='true';document.getElementById('appLoadingMessage').textContent='The page could not finish loading.';document.getElementById('appLoadingRetry').hidden=false;}
  const timeout=setTimeout(failed,15000);
  Promise.all([ready,loaded]).then(async()=>{
    if([...document.querySelectorAll('link[rel="stylesheet"]')].some(link=>!link.sheet))throw new Error('Styles unavailable');
    const logo=document.querySelector('.login-logo');
    if(logo?.decode)await logo.decode();
    clearTimeout(timeout);
    requestAnimationFrame(()=>{root.classList.remove('app-loading');root.classList.add('app-revealed');loading.hidden=true;});
  }).catch(()=>{clearTimeout(timeout);failed();});
})();

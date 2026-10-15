(() => {
  'use strict';
  if (window.__leonardoDiagnosticsLoaded) return;
  window.__leonardoDiagnosticsLoaded = true;

  const KEY = 'leonardoDiagnosticSessionV1';
  const MAX_EVENTS = 400;
  const MAX_BUTTONS = 22;
  let session = { recording: false, startedAt: null, events: [], page: '' };
  let observer = null;
  let ticker = null;
  let debounce = null;
  let lastFingerprint = '';
  let lastStored = Promise.resolve();

  const now = () => new Date().toISOString();
  const label = el => (el.getAttribute('aria-label') || el.getAttribute('title') || el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 90);
  const isVisible = el => {
    if (!(el instanceof Element)) return false;
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
  };
  const describe = el => ({
    tag: el.tagName.toLowerCase(),
    role: (el.getAttribute('role') || '').slice(0, 50),
    aria: (el.getAttribute('aria-label') || '').slice(0, 100),
    title: (el.getAttribute('title') || '').slice(0, 100),
    testid: (el.getAttribute('data-testid') || '').slice(0, 100),
    type: (el.getAttribute('type') || '').slice(0, 35),
    disabled: !!el.disabled || el.getAttribute('aria-disabled') === 'true',
    visible: isVisible(el)
  });
  function snapshot() {
    const fields = [...document.querySelectorAll('textarea, input, [contenteditable="true"], [role="textbox"]')]
      .filter(isVisible).slice(0, 10).map(el => ({
        tag: el.tagName.toLowerCase(),
        role: el.getAttribute('role') || '',
        placeholder: (el.getAttribute('placeholder') || el.getAttribute('data-placeholder') || '').slice(0, 110),
        chars: ((el.value ?? el.textContent) || '').length,
        hasText: !!((el.value ?? el.textContent) || '').trim(),
        contenteditable: el.getAttribute('contenteditable') || ''
      }));
    // No page text, input contents, image URLs, account details, or prompts in exported log.
    const buttons = [...document.querySelectorAll('button, [role="button"]')]
      .filter(isVisible)
      .map(el => ({el, text: label(el)}))
      .filter(({text,el}) => /generat|creat|image|video|cancel|stop|progress|loading|retry|download|ratio|model|auto|dynamic|seed|enhanc|result|batch|prompt|start|upscale/i.test(text + ' ' + (el.getAttribute('data-testid') || '')))
      .slice(0, MAX_BUTTONS).map(({el,text}) => ({...describe(el), caption: text}));
    const progress = [...document.querySelectorAll('[role="progressbar"], progress, [aria-busy="true"], [data-state="loading"]')]
      .filter(isVisible).slice(0, 10).map(el => ({...describe(el), value: (el.getAttribute('aria-valuenow') || '').slice(0, 20)}));
    const images = document.querySelectorAll('img').length;
    const videos = document.querySelectorAll('video').length;
    const busy = document.querySelectorAll('[aria-busy="true"]').length;
    const loaders = document.querySelectorAll('[role="progressbar"],progress').length;
    return { fields, buttons, progress, images, videos, busy, loaders, pageRoute: location.pathname };
  }
  function persist() {
    const data = structuredClone(session);
    lastStored = lastStored.catch(() => {}).then(() => chrome.storage.local.set({[KEY]: data}));
    return lastStored;
  }
  function record(kind, reason, force = false) {
    if (!session.recording) return;
    const data = snapshot();
    const fp = JSON.stringify(data);
    if (!force && fp === lastFingerprint) return;
    lastFingerprint = fp;
    session.events.push({time: now(), kind, reason, ...data});
    if (session.events.length > MAX_EVENTS) session.events.splice(0, session.events.length - MAX_EVENTS);
    persist();
  }
  function onMutations() {
    if (!session.recording) return;
    clearTimeout(debounce);
    debounce = setTimeout(() => record('ui-change', 'DOM update'), 300);
  }
  function beginWatch() {
    if (observer) return;
    observer = new MutationObserver(onMutations);
    observer.observe(document.documentElement, {subtree:true, childList:true, attributes:true, attributeFilter:['disabled','aria-disabled','aria-busy','aria-valuenow','data-state','class']});
    ticker = setInterval(() => record('poll', 'periodic check'), 1500);
  }
  function endWatch() {
    observer?.disconnect(); observer=null;
    clearInterval(ticker); ticker=null;
    clearTimeout(debounce); debounce=null;
  }
  chrome.storage.local.get(KEY).then(result => {
    if (result[KEY]) session = result[KEY];
    if (session.recording) { beginWatch(); record('reloaded', 'Content script attached', true); }
  });
  chrome.runtime.onMessage.addListener((msg, sender, respond) => {
    if (msg?.target !== 'leonardoDiagnostics') return;
    (async () => {
      try {
        if (msg.action === 'START') {
          endWatch();
          session = {recording:true, startedAt:now(), page:location.origin + location.pathname, events:[]};
          lastFingerprint='';
          beginWatch(); record('start', 'Recording started', true);
        } else if (msg.action === 'STOP') {
          record('stop', 'Recording stopped', true);
          session.recording=false; endWatch(); await persist();
        } else if (msg.action === 'MARK') record('manual-marker','User added checkpoint',true);
        else if (msg.action === 'CLEAR') { endWatch(); session={recording:false,startedAt:null,events:[],page:''}; lastFingerprint=''; await persist(); }
        respond({ok:true, recording:session.recording, count:session.events.length});
      } catch(e) {respond({ok:false,error:String(e?.message||e)});}
    })();
    return true;
  });
})();

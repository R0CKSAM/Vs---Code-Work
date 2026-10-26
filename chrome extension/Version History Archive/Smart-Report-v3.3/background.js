"use strict";
importScripts("company-config.js");

// ---------------------------------------------------------------------------
// Constants and helpers
// ---------------------------------------------------------------------------
const SCOPE = 'openid profile offline_access User.Read Mail.Send';
const ALARM = 'smart-report-next';
const GRAFANA_HOST = 'grafana-apj.trafficpeak.live';
const redirect = chrome.identity.getRedirectURL('');
const VIEWPORT = { width: 1600, height: 900 };       // fixed capture size: consistent, smaller files
const MAX_ATTACH_BYTES = 2.5 * 1024 * 1024;          // Graph single-request attachment limit is ~3 MB
const SIGNIN_MSG = 'Grafana is asking for sign-in. Open the Grafana tab, sign in, then retry.';

const POLICY = (typeof COMPANY_POLICY !== 'undefined') ? COMPANY_POLICY : {};
const ALLOWED_DOMAINS = (POLICY.allowedRecipientDomains || []).map(d => String(d).toLowerCase().replace(/^@/, ''));
const MAX_RECIPIENTS = Number(POLICY.maxRecipients) || 50;
// With no admin allowlist, reports are limited to the signed-in Outlook account domain.
// External recipient domains require explicit company-config.js approval.
const REQUIRE_PANELS = POLICY.requirePanels !== false;

const sleep = t => new Promise(r => setTimeout(r, t));
const b64url = b => btoa(String.fromCharCode(...new Uint8Array(b))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
const nonce = () => b64url(crypto.getRandomValues(new Uint8Array(32)));
const guid = x => /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(x || '');
const G = async keys => chrome.storage.local.get(keys);
const put = async x => chrome.storage.local.set(x);
// Short-lived access token lives in session storage (cleared when the browser closes).
const S = {
  get: keys => chrome.storage.session.get(keys),
  set: x => chrome.storage.session.set(x),
  remove: keys => chrome.storage.session.remove(keys)
};

const log = async (level, message) => {
  const d = await G(['logs']);
  const logs = d.logs || [];
  logs.push({ at: new Date().toISOString(), level, message: String(message).slice(0, 600) });
  await put({ logs: logs.slice(-120) });
};

async function notify(title, message) {
  try {
    await chrome.notifications.create({ type: 'basic', iconUrl: 'icon128.png', title, message });
  } catch (e) {
    await log('warn', 'Notification failed: ' + e.message);
  }
}

// Stored config merged with the company IDs (company IDs win when valid).
async function effectiveConfig() {
  const { config } = await G(['config']);
  const c = { ...(config || {}) };
  if (guid(COMPANY_MICROSOFT.clientId)) c.client = COMPANY_MICROSOFT.clientId;
  if (guid(COMPANY_MICROSOFT.tenantId)) c.tenant = COMPANY_MICROSOFT.tenantId;
  return c;
}

// ---------------------------------------------------------------------------
// Validation
// ---------------------------------------------------------------------------
function checkUrl(url) {
  const u = new URL(url);
  if (u.protocol !== 'https:' || u.hostname !== GRAFANA_HOST || !u.pathname.startsWith('/d/'))
    throw Error('Use a dashboard URL at https://' + GRAFANA_HOST + '/d/...');
  return u.href;
}

// "/d/<uid>" identifies a dashboard regardless of slug or query string.
function dashKey(url) {
  try { return new URL(url).pathname.split('/').filter(Boolean).slice(0, 2).join('/'); } catch { return ''; }
}
function isDashboardTab(url, dashboard) {
  try {
    const current = new URL(url), expected = new URL(dashboard);
    if (current.protocol !== 'https:' || current.hostname !== GRAFANA_HOST || dashKey(url) !== dashKey(dashboard)) return false;
    // A screenshot is valid only for the saved dashboard filters/time range.
    // Ignore additional Grafana-generated query parameters not requested by the user.
    for (const key of new Set(expected.searchParams.keys())) {
      const a = current.searchParams.getAll(key).sort();
      const b = expected.searchParams.getAll(key).sort();
      if (a.length !== b.length || a.some((v, i) => v !== b[i])) return false;
    }
    return true;
  } catch { return false; }
}

function parseEmails(raw, permittedDomains = null) {
  // Accept newline/comma/semicolon/space-separated addresses and Outlook-style
  // "Person Name <person@example.com>" paste formats; do not discard older entries.
  const input = String(raw || '').replace(/(?:"[^"\n]+"|[^,;\n<>]+)\s*<\s*([^<>\s]+@[^<>\s]+)\s*>/g, '$1');
  const seen = new Set(), out = [];
  for (const email of input.split(/[,;\s]+/).filter(Boolean)) {
    if (!/^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$/.test(email)) throw Error('Invalid email address: ' + email);
    const key = email.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    if (permittedDomains && !permittedDomains.includes(key.split('@')[1]))
      throw Error('Recipient not allowed: ' + email + '. Allowed email domain(s): ' + permittedDomains.join(', ') + '.');
    out.push({ emailAddress: { address: email } });
  }
  return out;
}

function checkCaptureConfig(c) {
  checkUrl(c.dashboard);
  if (!Number.isInteger(+c.settle) || +c.settle < 2 || +c.settle > 120) throw Error('Panel settling delay must be 2–120 seconds.');
}
function checkConfig(c) {
  if (!guid(c.client) || !guid(c.tenant)) throw Error('Company Microsoft IDs are missing or invalid in company-config.js.');
  checkCaptureConfig(c);
  const to = parseEmails(c.to), cc = parseEmails(c.cc), bcc = parseEmails(c.bcc);
  if (!to.length) throw Error('At least one To recipient is required.');
  if (to.length + cc.length + bcc.length > MAX_RECIPIENTS) throw Error('Too many recipients (limit ' + MAX_RECIPIENTS + ').');
  if (!Number.isInteger(+c.interval) || +c.interval < 1 || +c.interval > 1440) throw Error('Interval must be 1–1440 minutes.');
}

// ---------------------------------------------------------------------------
// Microsoft sign-in (OAuth code flow + PKCE, public client, no secret)
// ---------------------------------------------------------------------------
async function tokenRequest(tenant, params) {
  const r = await fetch(`https://login.microsoftonline.com/${tenant}/oauth2/v2.0/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams(params)
  });
  let j = {};
  try { j = await r.json(); } catch { /* non-JSON error body */ }
  if (!r.ok) {
    const e = Error(j.error_description || j.error || 'Microsoft token exchange failed (' + r.status + ')');
    e.code = j.error;
    throw e;
  }
  return j;
}

async function saveTokens(j) {
  const prior = await G(['tokens']);
  await S.set({ access: { token: j.access_token, expiresAt: Date.now() + Math.max(30, j.expires_in - 120) * 1000 } });
  await put({ tokens: { refresh: j.refresh_token || prior.tokens?.refresh || null } });
}

async function auth(interactive = true) {
  const c = await effectiveConfig();
  if (!guid(c.client) || !guid(c.tenant)) throw Error('Configure Microsoft application IDs first.');
  const verifier = nonce(), state = nonce();
  const challenge = b64url(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier)));
  const u = new URL(`https://login.microsoftonline.com/${c.tenant}/oauth2/v2.0/authorize`);
  u.search = new URLSearchParams({
    client_id: c.client, response_type: 'code', redirect_uri: redirect, response_mode: 'query',
    scope: SCOPE, state, code_challenge: challenge, code_challenge_method: 'S256',
    prompt: interactive ? 'select_account' : 'none'
  }).toString();
  const cb = await chrome.identity.launchWebAuthFlow({ url: u.href, interactive });
  if (!cb) throw Error('Microsoft authorization returned no URL');
  const p = new URL(cb).searchParams;
  if (p.get('error')) throw Error(p.get('error_description') || p.get('error'));
  if (p.get('state') !== state) throw Error('OAuth state mismatch');
  if (!p.get('code')) throw Error('No authorization code returned');
  const j = await tokenRequest(c.tenant, {
    client_id: c.client, grant_type: 'authorization_code', code: p.get('code'),
    redirect_uri: redirect, code_verifier: verifier, scope: SCOPE
  });
  await saveTokens(j);
  await log('info', 'Microsoft Outlook account connected');
  return 'Microsoft connected';
}

async function getAccess() {
  const c = await effectiveConfig();
  const { access } = await S.get('access');
  if (access?.token && access.expiresAt > Date.now() + 60000) return access.token;

  const { tokens } = await G(['tokens']);
  if (tokens?.refresh && guid(c.client) && guid(c.tenant)) {
    try {
      const j = await tokenRequest(c.tenant, {
        client_id: c.client, grant_type: 'refresh_token', refresh_token: tokens.refresh, scope: SCOPE
      });
      await saveTokens(j);
      return j.access_token;
    } catch (e) {
      await log('warn', 'Silent token renewal unavailable: ' + e.message);
      // A refresh token Microsoft rejected is useless: forget it so the popup shows "Sign-in required".
      if (['invalid_grant', 'interaction_required', 'consent_required'].includes(e.code)) await put({ tokens: { refresh: null } });
    }
  }
  try {
    await auth(false);
    const { access: a } = await S.get('access');
    return a.token;
  } catch {
    throw Error('Microsoft session needs renewal. Open Smart Report and click Connect Outlook.');
  }
}

// ---------------------------------------------------------------------------
// Grafana tab handling and capture
// ---------------------------------------------------------------------------
// Returns the tab showing the CONFIGURED dashboard. Never picks some other Grafana dashboard.
async function getDashboardTab(c) {
  const { tabId } = await G(['tabId']);
  let t = null;
  if (tabId) { try { t = await chrome.tabs.get(tabId); } catch { /* tab gone */ } }
  if (t && isDashboardTab(t.url, c.dashboard)) return { tab: t, created: false };
  const tabs = await chrome.tabs.query({ url: `https://${GRAFANA_HOST}/*` });
  t = tabs.find(x => isDashboardTab(x.url, c.dashboard));
  if (t) return { tab: t, created: false };
  const created = await chrome.tabs.create({ url: checkUrl(c.dashboard), active: false, pinned: true });
  return { tab: created, created: true };
}

async function waitLoaded(tabId, maxMs = 90000) {
  const deadline = Date.now() + maxMs;
  while (Date.now() < deadline) {
    let tab;
    try { tab = await chrome.tabs.get(tabId); } catch { throw Error('Grafana tab closed'); }
    if (tab.status === 'complete') return;
    await sleep(900);
  }
  throw Error('Dashboard navigation timed out');
}

// Reload and wait for the reload itself to finish (not the old page's "complete" state).
function reloadAndWait(tabId, maxMs = 90000) {
  return new Promise((resolve, reject) => {
    let sawLoading = false;
    const onUpdated = (id, info) => {
      if (id !== tabId) return;
      if (info.status === 'loading') sawLoading = true;
      if (info.status === 'complete' && sawLoading) { cleanup(); resolve(); }
    };
    const onRemoved = id => { if (id === tabId) { cleanup(); reject(Error('Grafana tab closed')); } };
    const timer = setTimeout(() => { cleanup(); reject(Error('Dashboard navigation timed out')); }, maxMs);
    // If the reload finished so quickly that we missed the "loading" event, fall back to polling.
    const fallback = setTimeout(async () => {
      if (sawLoading) return;
      const tab = await chrome.tabs.get(tabId).catch(() => null);
      if (tab && tab.status === 'complete') { cleanup(); resolve(); } else sawLoading = true;
    }, 4000);
    function cleanup() {
      clearTimeout(timer); clearTimeout(fallback);
      chrome.tabs.onUpdated.removeListener(onUpdated);
      chrome.tabs.onRemoved.removeListener(onRemoved);
    }
    chrome.tabs.onUpdated.addListener(onUpdated);
    chrome.tabs.onRemoved.addListener(onRemoved);
    Promise.resolve(chrome.tabs.reload(tabId, { bypassCache: false })).catch(e => { cleanup(); reject(e); });
  });
}

async function inspectPage(tabId) {
  try {
    const results = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => {
        const visible = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
        const busy = [...document.querySelectorAll('[aria-busy="true"],.panel-loading,.loading-indicator,[data-testid*="loading"],.fa-spinner')].filter(visible).length;
        const panels = document.querySelectorAll('[data-panelid],[data-viz-panel-key],[data-testid="panel-header-container"],.react-grid-item').length;
        const loginForm = !!document.querySelector('input[type="password"],form[action*="login"]');
        return { href: location.href, path: location.pathname, busy, panels, loginForm, ready: document.readyState };
      }
    });
    return results[0]?.result || null;
  } catch {
    return null; // treated as "not ready" (fail closed)
  }
}

async function waitForPanels(tabId, c, afterResize = false) {
  await sleep(afterResize ? 2500 : Math.max(2, +c.settle || 12) * 1000);
  let clear = 0, last = null;
  for (let i = 0; i < (afterResize ? 12 : 20); i++) {
    let tab;
    try { tab = await chrome.tabs.get(tabId); } catch { throw Error('Grafana tab closed'); }
    if (new URL(tab.url).hostname !== GRAFANA_HOST || new URL(tab.url).pathname.startsWith('/login')) throw Error(SIGNIN_MSG);
    const r = await inspectPage(tabId);
    last = r;
    if (r) {
      if (r.loginForm || r.path.startsWith('/login')) throw Error(SIGNIN_MSG);
      if (!isDashboardTab(r.href, c.dashboard)) throw Error('Grafana dashboard or time/filter parameters do not match the saved URL; screenshot not sent. Reopen the saved dashboard URL.');
    }
    const ok = r && r.ready === 'complete' && r.busy === 0 && (!REQUIRE_PANELS || r.panels > 0);
    clear = ok ? clear + 1 : 0;
    if (clear >= 3) return r;
    await sleep(afterResize ? 1000 : 1500);
  }
  if (REQUIRE_PANELS && last && last.panels === 0) throw Error('No Grafana panels found on the page; screenshot not sent');
  throw Error('Grafana panels still show loading indicators; screenshot not sent');
}

async function captureTab(tabId, c) {
  const target = { tabId };
  const attempts = [
    { format: 'png', ext: 'png', mime: 'image/png' },
    { format: 'jpeg', quality: 85, ext: 'jpg', mime: 'image/jpeg' },
    { format: 'jpeg', quality: 60, ext: 'jpg', mime: 'image/jpeg' }
  ];
  let attached = false, result = null;
  try {
    await chrome.debugger.attach(target, '1.3');
    attached = true;
    const cmd = (m, p) => chrome.debugger.sendCommand(target, m, p);
    await cmd('Page.enable');
    // Best effort: keep the background tab rendering and use a fixed viewport.
    for (const [m, p] of [
      ['Emulation.setFocusEmulationEnabled', { enabled: true }],
      ['Page.setWebLifecycleState', { state: 'active' }],
      ['Emulation.setDeviceMetricsOverride', { ...VIEWPORT, deviceScaleFactor: 1, mobile: false }]
    ]) { try { await cmd(m, p); } catch { /* optional */ } }
    await progress('Rechecking resized Grafana panels', 65);
    await waitForPanels(tabId, c, true); // wait for real re-render, not just a fixed timer
    await progress('Capturing screenshot', 76);
    for (const a of attempts) {
      const res = await cmd('Page.captureScreenshot', {
        format: a.format, ...(a.quality ? { quality: a.quality } : {}), captureBeyondViewport: false, fromSurface: true
      });
      if (!res?.data || res.data.length < 1200) throw Error('Empty screenshot returned');
      if (res.data.length * 0.75 <= MAX_ATTACH_BYTES) { result = { data: res.data, ext: a.ext, mime: a.mime }; break; }
    }
  } catch (e) {
    throw Error('Background screenshot failed: ' + e.message + '. Close DevTools on the Grafana tab, do not dismiss the "debugging" bar during a capture, and check the Chrome debugger policy.');
  } finally {
    if (attached) {
      try { await chrome.debugger.sendCommand(target, 'Emulation.clearDeviceMetricsOverride'); } catch { /* ignore */ }
      try { await chrome.debugger.detach(target); } catch { /* ignore */ }
    }
  }
  if (!result) throw Error('Screenshot is over the 3 MB email attachment limit even after compression');
  return result;
}

async function screenshot(c, shouldReload) {
  await progress('Opening Grafana dashboard', 18);
  const { tab, created } = await getDashboardTab(c);
  await put({ tabId: tab.id });
  if (created) await waitLoaded(tab.id);
  else if (shouldReload) await reloadAndWait(tab.id);
  else if (tab.status !== 'complete') await waitLoaded(tab.id);
  await progress('Waiting for dashboard panels', 38);
  await waitForPanels(tab.id, c);
  await progress('Preparing screenshot', 58);
  const shot = await captureTab(tab.id, c);
  return { ...shot, tabId: tab.id };
}

// ---------------------------------------------------------------------------
// Email through Microsoft Graph
// ---------------------------------------------------------------------------
async function email(c, shot, test) {
  const token = await getAccess();
  // If the admin has not supplied an allowlist, fail closed to the signed-in
  // corporate Outlook domain instead of silently permitting external sharing.
  let permittedDomains = ALLOWED_DOMAINS;
  if (!permittedDomains.length) {
    const userResponse = await fetch('https://graph.microsoft.com/v1.0/me?$select=mail,userPrincipalName', {
      headers: { Authorization: 'Bearer ' + token }
    });
    if (!userResponse.ok) throw Error('Could not verify Outlook sender domain (Microsoft Graph ' + userResponse.status + ').');
    const me = await userResponse.json();
    const domain = String(me.mail || me.userPrincipalName || '').split('@')[1]?.toLowerCase();
    if (!domain) throw Error('Outlook account has no verifiable email domain. Ask IT to configure allowedRecipientDomains.');
    permittedDomains = [domain];
  }
  const stamp = new Date().toLocaleString('sv-SE', { timeZone: 'Asia/Kolkata' }).replace(' ', '_').replace(/:/g, '-');
  const name = `Grafana_Report_${stamp}_IST.${shot.ext}`;
  const subject = (c.subject || 'Grafana Dashboard Report · {time}').replaceAll('{time}', new Date().toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' }));
  const recipients = {
    toRecipients: parseEmails(c.to, permittedDomains),
    ccRecipients: parseEmails(c.cc, permittedDomains),
    bccRecipients: parseEmails(c.bcc, permittedDomains)
  };
  const msg = {
    message: {
      subject: (test ? '[TEST] ' : '') + subject,
      body: {
        contentType: 'Text',
        content: `Smart Report ${test ? 'test' : 'scheduled'} dashboard screenshot.\nCapture: ${new Date().toISOString()}\nDashboard: ${checkUrl(c.dashboard)}\nAutomated email from signed-in Microsoft 365 account.`
      },
      ...recipients,
      attachments: [{ '@odata.type': '#microsoft.graph.fileAttachment', name, contentType: shot.mime, contentBytes: shot.data }]
    },
    saveToSentItems: true
  };
  const r = await fetch('https://graph.microsoft.com/v1.0/me/sendMail', {
    method: 'POST',
    headers: { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' },
    body: JSON.stringify(msg)
  });
  if (!r.ok) {
    let reason = await r.text();
    try { reason = JSON.parse(reason).error?.message || reason; } catch { /* keep raw text */ }
    throw Error('Graph ' + r.status + ': ' + reason.slice(0, 280));
  }
  return { name, to: recipients.toRecipients.length, cc: recipients.ccRecipients.length, bcc: recipients.bccRecipients.length };
}

let busy = false;
let currentRun = null;
async function progress(stage, percent) {
  if (!currentRun) return;
  const state = { ...currentRun, stage, percent, busy: true, updatedAt: Date.now() };
  await put({ runState: state, lastStatus: stage });
}
async function finishProgress(stage, ok, error = '') {
  if (!currentRun) return;
  await put({ runState: { ...currentRun, stage, busy: false, percent: ok ? 100 : 0,
    updatedAt: Date.now(), error } });
}
async function run(test = false, captureOnly = false) {
  if (busy) throw Error('Report capture already in progress');
  busy = true;
  currentRun = { kind: captureOnly ? 'preview' : test ? 'test' : 'scheduled', startedAt: Date.now() };
  // A Chrome extension API call during long panel waits prevents the normal
  // service-worker idle cutoff. Chrome may still suspend/discard background tabs.
  const keepAlive = setInterval(() => chrome.runtime.getPlatformInfo().catch(() => {}), 20000);
  try {
    await progress('Checking configuration', 5);
    const c = await effectiveConfig();
    captureOnly ? checkCaptureConfig(c) : checkConfig(c);
    await put({ lastError: '' });
    const shot = await screenshot(c, true);
    if (captureOnly) {
      await finishProgress('Preview ready', true);
      await log('info', 'Grafana screenshot preview captured successfully');
      return { preview: `data:${shot.mime};base64,${shot.data}` };
    }
    if (!test && (await G(['mode'])).mode !== 'running') throw Error('Monitoring was paused or stopped before email was sent.');
    await progress('Sending via Outlook', 87);
    const res = await email(c, shot, test);
    const { sent } = await G(['sent']);
    await put({ sent: (sent || 0) + 1, lastSent: new Date().toISOString(),
      lastStatus: 'Microsoft Graph accepted email for delivery', lastError: '', consecutiveFailures: 0 });
    await finishProgress('Email accepted for delivery', true);
    await log('success', `${test ? 'Test' : 'Scheduled'} report accepted, To ${res.to}, CC ${res.cc}, BCC ${res.bcc}`);
    return { message: 'Graph accepted the email; confirm receipt in Outlook.' };
  } catch (e) {
    await put({ lastError: e.message, lastStatus: 'Report failed: ' + e.message });
    await finishProgress('Report failed', false, e.message);
    await log('error', e.message);
    throw e;
  } finally {
    clearInterval(keepAlive);
    busy = false;
    currentRun = null;
  }
}

// ---------------------------------------------------------------------------
// Scheduling
// ---------------------------------------------------------------------------
async function schedule(mode) {
  if (mode === 'running') {
    const c = await effectiveConfig();
    checkConfig(c);
    if (!(await G(['tokens'])).tokens?.refresh) throw Error('Connect Outlook before starting monitoring.');
    await chrome.alarms.clear(ALARM);
    await chrome.alarms.create(ALARM, { periodInMinutes: +c.interval, delayInMinutes: +c.interval });
    await put({ consecutiveFailures: 0 });
  } else {
    await chrome.alarms.clear(ALARM); // pausing/stopping never depends on the config being valid
  }
  await put({ mode, lastStatus: mode === 'running' ? 'Monitoring started' : 'Monitoring ' + mode });
  await log('info', 'Monitoring ' + mode);
  return mode;
}

// Alarms can be cleared by an extension update/reload or a browser restart: put it back if we should be running.
async function restoreAlarm() {
  const { mode } = await G(['mode']);
  if (mode !== 'running') return;
  const c = await effectiveConfig();
  const m = Math.max(1, Number(c.interval) || 15);
  const existing = await chrome.alarms.get(ALARM);
  if (existing && existing.periodInMinutes === m) return;
  await chrome.alarms.clear(ALARM);
  await chrome.alarms.create(ALARM, { periodInMinutes: m, delayInMinutes: m });
  await log('info', 'Schedule restored after extension or browser restart');
}

chrome.alarms.onAlarm.addListener(async a => {
  if (a.name !== ALARM) return;
  const { mode } = await G(['mode']);
  if (mode !== 'running') return;
  try {
    await run(false, false);
  } catch (e) {
    if (/Microsoft session needs renewal/.test(e.message)) {
      await schedule('paused');
      await notify('Smart Report needs sign-in', 'Reconnect Outlook to resume automated email reports.');
      return;
    }
    if (/already in progress/.test(e.message)) return;
    const { consecutiveFailures } = await G(['consecutiveFailures']);
    const n = (consecutiveFailures || 0) + 1;
    await put({ consecutiveFailures: n });
    if (n === 1 || n % 4 === 0)
      await notify('Smart Report: report not sent', (n > 1 ? n + ' failures in a row. ' : '') + String(e.message).slice(0, 150));
  }
});

chrome.runtime.onStartup.addListener(() => restoreAlarm().catch(e => log('error', 'Schedule restore failed: ' + e.message)));
chrome.runtime.onInstalled.addListener(() => restoreAlarm().catch(e => log('error', 'Schedule restore failed: ' + e.message)));
restoreAlarm().catch(e => log('error', 'Schedule restore failed: ' + e.message));

// ---------------------------------------------------------------------------
// Messages from the popup
// ---------------------------------------------------------------------------
const CONFIG_KEYS = ['dashboard', 'to', 'cc', 'bcc', 'subject', 'interval', 'settle'];

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  // Only our own extension pages may drive the worker.
  if (sender.id !== chrome.runtime.id || (sender.url && !sender.url.startsWith(chrome.runtime.getURL('')))) {
    reply({ ok: false, error: 'Unauthorized sender' });
    return false;
  }
  (async () => {
    switch (msg.action) {
      case 'GET': {
        const d = await G(['config', 'mode', 'sent', 'lastSent', 'lastStatus', 'lastError', 'tokens', 'consecutiveFailures', 'runState', 'logs']);
        const a = await chrome.alarms.get(ALARM);
        return {
          config: d.config, mode: d.mode, sent: d.sent, lastSent: d.lastSent, lastStatus: d.lastStatus, lastError: d.lastError,
          consecutiveFailures: d.consecutiveFailures || 0,
          companyConfigured: guid(COMPANY_MICROSOFT.clientId) && guid(COMPANY_MICROSOFT.tenantId),
          connected: !!d.tokens?.refresh,
          allowedDomains: ALLOWED_DOMAINS,
          senderDomainOnly: !ALLOWED_DOMAINS.length,
          events: (d.logs || []).slice(-3).reverse(),
          runState: d.runState?.busy && Date.now() - d.runState.updatedAt > 300000
            ? { ...d.runState, busy: false, stage: 'Previous run interrupted', percent: 0,
                error: 'Chrome interrupted the last capture. Review logs and retry.' } : d.runState,
          redirect, nextRun: a?.scheduledTime || null
        };
      }
      case 'CONFIG': {
        const old = await G(['config']);
        const incoming = {};
        for (const k of CONFIG_KEYS) if (msg.config && k in msg.config) incoming[k] = msg.config[k];
        const updated = { ...(old.config || {}), ...incoming };
        if (guid(COMPANY_MICROSOFT.clientId)) updated.client = COMPANY_MICROSOFT.clientId;
        if (guid(COMPANY_MICROSOFT.tenantId)) updated.tenant = COMPANY_MICROSOFT.tenantId;
        // Allow autosaving partial drafts; full checks happen only for Send/Start.
        await put({ config: updated });
        if ((await G(['mode'])).mode === 'running' && String(old.config?.interval) !== String(updated.interval)) {
          const interval = Number(updated.interval);
          if (Number.isInteger(interval) && interval >= 1 && interval <= 1440) {
            await chrome.alarms.clear(ALARM);
            await chrome.alarms.create(ALARM, { periodInMinutes: interval, delayInMinutes: interval });
            await put({ lastStatus: 'Schedule updated to every ' + interval + ' minutes' });
            await log('info', 'Schedule updated: every ' + interval + ' minutes');
          }
        }
        return { ok: true };
      }
      case 'LOGIN': return { message: await auth(true) };
      case 'LOGOUT': {
        await schedule('paused');
        await S.remove('access');
        await put({ tokens: { refresh: null } });
        await log('info', 'Outlook disconnected by user');
        return { message: 'Outlook disconnected. Monitoring is paused.' };
      }
      case 'START': return { mode: await schedule('running') };
      case 'PAUSE': return { mode: await schedule('paused') };
      case 'RESUME': return { mode: await schedule('running') };
      case 'STOP': return { mode: await schedule('stopped') };
      case 'TEST': return await run(true, false);
      case 'CAPTURE': return await run(false, true);
      case 'USE_TAB': {
        if (!Number.isInteger(msg.tabId)) throw Error('Open the Grafana dashboard tab, click the extension icon from that tab, then try again.');
        const tab = await chrome.tabs.get(msg.tabId);
        const url = checkUrl(tab.url || msg.url);
        await put({ tabId: msg.tabId });
        return { url };
      }
      case 'OPEN_TAB': {
        const c = await effectiveConfig();
        const tab = await chrome.tabs.create({ url: checkUrl(c.dashboard), active: true });
        await put({ tabId: tab.id });
        return { ok: true };
      }
      case 'LOGS': {
        const { logs } = await G(['logs']);
        return { logs: logs || [] };
      }
      default: throw Error('Unknown action');
    }
  })().then(result => reply({ ok: true, result })).catch(err => reply({ ok: false, error: String(err.message || err) }));
  return true;
});

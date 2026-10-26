"use strict";
importScripts("company-config.js", "capture-engine.js");


// ---------------------------------------------------------------------------
// Constants and helpers
// ---------------------------------------------------------------------------
const SCOPE = 'openid profile offline_access User.Read Mail.Send';
const ALARM = 'smart-report-next';
const GRAFANA_HOST = 'grafana-apj.trafficpeak.live';
const redirect = chrome.identity.getRedirectURL('');
const MAX_ATTACH_BYTES = 2.5 * 1024 * 1024;          // Graph single-request attachment limit is ~3 MB
const SIGNIN_MSG = 'Grafana is asking for sign-in. Open the Grafana tab, sign in, then retry.';

const POLICY = (typeof COMPANY_POLICY !== 'undefined') ? COMPANY_POLICY : {};
const ALLOWED_DOMAINS = (POLICY.allowedRecipientDomains || []).map(d => String(d).toLowerCase().replace(/^@/, ''));
const MAX_RECIPIENTS = Number(POLICY.maxRecipients) || 50;
const DEFAULT_PANEL_DELAY = 12; // internal safety default; never an editable setting
const DEFAULT_SUBJECT = 'Grafana Dashboard Report · {time}';
// With no admin allowlist, reports are limited to the signed-in Outlook account domain.
// External recipient domains require explicit company-config.js approval.
const REQUIRE_PANELS = POLICY.requirePanels !== false;
const DASHBOARD_DEFAULTS = (typeof COMPANY_GRAFANA_DEFAULTS !== 'undefined') ? COMPANY_GRAFANA_DEFAULTS : {};
const DEFAULT_GRAFANA_FROM = String(DASHBOARD_DEFAULTS.defaultFrom || 'now/d');
const DEFAULT_GRAFANA_TO = String(DASHBOARD_DEFAULTS.defaultTo || 'now');
const DEFAULT_GRAFANA_REFRESH = String(DASHBOARD_DEFAULTS.defaultRefresh || '1m');
const IGNORED_URL_PARAMETERS = new Set(DASHBOARD_DEFAULTS.ignoreUrlParameters || ['var-hdx_query_errors']);

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
    await chrome.notifications.create('smart-report-status', { type: 'basic', iconUrl: 'icon128.png', title, message });
  } catch (e) {
    await log('warn', 'Notification failed: ' + e.message);
  }
}

// Stored config merged with the company IDs (company IDs win when valid).
async function effectiveConfig() {
  const { config } = await G(['config']);
  const c = { interval: 15, subject: DEFAULT_SUBJECT, expandRows: DASHBOARD_DEFAULTS.expandAllRows !== false, ...(config || {}) };
  // v3.3/v3.3.1 could store an empty delay as zero. Normalize unconditionally.
  // The user never needs to configure panel settling manually.
  c.settle = DEFAULT_PANEL_DELAY;
  // v3.4 sends ONLY to explicitly visible To recipients. Any legacy hidden
  // CC/BCC settings are intentionally ignored, preventing surprise delivery.
  c.cc = ''; c.bcc = '';
  if (guid(COMPANY_MICROSOFT.clientId)) c.client = COMPANY_MICROSOFT.clientId;
  if (guid(COMPANY_MICROSOFT.tenantId)) c.tenant = COMPANY_MICROSOFT.tenantId;
  if (c.dashboard) { try { c.dashboard = checkUrl(c.dashboard); } catch { /* validated later */ } }
  return c;
}

// ---------------------------------------------------------------------------
// Validation
// ---------------------------------------------------------------------------
function normalizeDashboardUrl(url) {
  const u = new URL(url);
  if (!u.searchParams.has('from')) u.searchParams.set('from', DEFAULT_GRAFANA_FROM);
  if (!u.searchParams.has('to')) u.searchParams.set('to', DEFAULT_GRAFANA_TO);
  if (!u.searchParams.has('refresh')) u.searchParams.set('refresh', DEFAULT_GRAFANA_REFRESH);
  return u;
}
function checkUrl(url) {
  const u = normalizeDashboardUrl(url);
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
    const raw = new URL(url), expected = normalizeDashboardUrl(dashboard), current = normalizeDashboardUrl(url);
    if (raw.protocol !== 'https:' || raw.hostname !== GRAFANA_HOST || dashKey(url) !== dashKey(dashboard)) return false;
    // Check actual data filters in both directions. Ignore only the explicitly
    // configured, observed diagnostic URL field; never ignore all var-* values.
    const keys = new Set([...expected.searchParams.keys(), ...current.searchParams.keys()].filter(k =>
      !IGNORED_URL_PARAMETERS.has(k) && (expected.searchParams.has(k) || k.startsWith('var-') || ['orgId','from','to','timezone','refresh','time','time.window'].includes(k))));
    for (const key of keys) {
      const a=current.searchParams.getAll(key).sort(), b=expected.searchParams.getAll(key).sort();
      if (a.length !== b.length || a.some((v,i)=>v !== b[i])) return false;
    }
    return !['viewPanel','editPanel','inspect','editview'].some(k=>current.searchParams.has(k));
  } catch { return false; }
}
function captureSignature(c) {
  const u=normalizeDashboardUrl(c.dashboard);
  for(const k of IGNORED_URL_PARAMETERS)u.searchParams.delete(k);
  u.searchParams.sort();
  return JSON.stringify({version:'3.7.5', url:u.href, rows:c.expandRows!==false?'all':'current', width:1600});
}
function safeCaptureSignature(c){try{return captureSignature(c);}catch{return '';}}
async function requireApprovedPreview(c) {
  const d=await G(['approvedCaptureSignature']);
  if(d.approvedCaptureSignature!==captureSignature(c))throw Error('Check screenshot first, then approve it in the preview tab. Email is blocked until you review the new capture layout.');
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

// De-duplicate across all fields as well as within each field, matching popup.
// The first occurrence wins: To has precedence, then CC, then BCC.
function parseRecipients(c, permittedDomains = null) {
  const seen = new Set(), groups = {};
  for (const type of ['to', 'cc', 'bcc']) {
    groups[type] = parseEmails(c[type], permittedDomains).filter(entry => {
      const key = entry.emailAddress.address.toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }
  return groups;
}

function checkCaptureConfig(c) {
  checkUrl(c.dashboard);
  // Auto-managed: no editable delay and no validation failure for old settings.
}
function checkConfig(c) {
  if (!guid(c.client) || !guid(c.tenant)) throw Error('Company Microsoft IDs are missing or invalid in company-config.js.');
  checkCaptureConfig(c);
  // Check admin-approved domains before loading the dashboard: fail quickly.
  const {to, cc, bcc} = parseRecipients(c, ALLOWED_DOMAINS.length ? ALLOWED_DOMAINS : null);
  if (!to.length) throw Error('At least one To recipient is required.');
  if (to.length + cc.length + bcc.length > MAX_RECIPIENTS) throw Error('Too many recipients (limit ' + MAX_RECIPIENTS + ').');
  if (!Number.isInteger(+c.interval) || +c.interval < 1 || +c.interval > 1440) throw Error('Choose a reporting interval between 1 and 1440 minutes.');
}

// ---------------------------------------------------------------------------
// Microsoft sign-in (OAuth code flow + PKCE, public client, no secret)
// ---------------------------------------------------------------------------
// Authentication policy is separate from recipient policy.
function approvedTenants() {
  return (COMPANY_MICROSOFT.allowedTenantIds || [COMPANY_MICROSOFT.tenantId]).map(x=>String(x).toLowerCase());
}
function validStoredIdentity(tokens) {
  return tokens?.identityVersion === 1 && tokens.client === COMPANY_MICROSOFT.clientId &&
    approvedTenants().includes(tokens.tenant);
}
function jwtBytes(part) {
  const s=part.replace(/-/g,'+').replace(/_/g,'/');
  return Uint8Array.from(atob(s.padEnd(Math.ceil(s.length/4)*4,'=')),c=>c.charCodeAt(0));
}
async function validateMicrosoftIdentity(token, client, expectedNonce) {
  if(typeof token!=='string'||token.length>50000)throw Error('Microsoft returned no valid identity token.');
  const parts=token.split('.');
  if(parts.length!==3)throw Error('Invalid identity token format.');
  const header=JSON.parse(new TextDecoder().decode(jwtBytes(parts[0])));
  const claims=JSON.parse(new TextDecoder().decode(jwtBytes(parts[1])));
  const tenant=String(claims.tid||'').toLowerCase(),now=Date.now()/1000;
  if(header.alg!=='RS256'||!header.kid||!guid(tenant)||!approvedTenants().includes(tenant))
    throw Error('This Microsoft organization is not approved for Smart Report.');
  const issuer='https://login.microsoftonline.com/'+tenant+'/v2.0';
  if(claims.iss!==issuer||claims.aud!==client||claims.ver!=='2.0'||
     typeof claims.exp!=='number'||claims.exp<=now||
     typeof claims.nbf!=='number'||claims.nbf>now+120||
     typeof claims.sub!=='string'||!claims.sub||
     !expectedNonce||claims.nonce!==expectedNonce)
    throw Error('Microsoft identity validation failed. Sign in again.');
  // Only retrieve metadata/keys from the pinned Microsoft host, never token URLs.
  const getJson=async url=>{
    const r=await fetch(url,{signal:AbortSignal.timeout(15000),redirect:'error'});
    if(!r.ok)throw Error('Could not verify Microsoft signing keys. Retry sign-in.');
    return r.json();
  };
  const metadata=await getJson('https://login.microsoftonline.com/'+tenant+'/v2.0/.well-known/openid-configuration');
  const keysUrl=new URL(metadata.jwks_uri);
  if(metadata.issuer!==issuer||keysUrl.origin!=='https://login.microsoftonline.com'||keysUrl.username||keysUrl.password)
    throw Error('Unexpected Microsoft identity metadata.');
  const jwks=await getJson(keysUrl.href);
  const key=jwks.keys?.find(k=>k.kid===header.kid&&k.kty==='RSA'&&k.use==='sig'&&
    (!k.issuer||k.issuer.replace('{tenantid}',tenant)===issuer));
  if(!key)throw Error('Microsoft signing key unavailable. Retry sign-in.');
  const publicKey=await crypto.subtle.importKey('jwk',key,{name:'RSASSA-PKCS1-v1_5',hash:'SHA-256'},false,['verify']);
  if(!await crypto.subtle.verify('RSASSA-PKCS1-v1_5',publicKey,jwtBytes(parts[2]),new TextEncoder().encode(parts[0]+'.'+parts[1])))
    throw Error('Microsoft identity signature is invalid.');
  return tenant;
}
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

async function saveTokens(j, identity = null) {
  const prior = await G(['tokens']);
  await S.set({ access: { token: j.access_token, expiresAt: Date.now() + Math.max(30, j.expires_in - 120) * 1000 } });
  await put({ tokens: { ...(identity || prior.tokens), refresh: j.refresh_token || (identity ? null : prior.tokens?.refresh) || null } });
}

async function auth(interactive = true) {
  const c = await effectiveConfig();
  if (!guid(c.client) || !guid(c.tenant)) throw Error('Configure Microsoft application IDs first.');
  const verifier = nonce(), state = nonce(), loginNonce = nonce();
  const challenge = b64url(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier)));
  const authority = COMPANY_MICROSOFT.authority === 'organizations' ? 'organizations' : c.tenant;
  const u = new URL(`https://login.microsoftonline.com/${authority}/oauth2/v2.0/authorize`);
  u.search = new URLSearchParams({
    client_id: c.client, response_type: 'code', redirect_uri: redirect, response_mode: 'query',
    scope: SCOPE, state, nonce: loginNonce, code_challenge: challenge, code_challenge_method: 'S256',
    prompt: interactive ? 'select_account' : 'none'
  }).toString();
  const cb = await chrome.identity.launchWebAuthFlow({ url: u.href, interactive });
  if (!cb) throw Error('Microsoft authorization returned no URL');
  const callback = new URL(cb), expectedRedirect = new URL(redirect);
  if(callback.origin!==expectedRedirect.origin||callback.pathname!==expectedRedirect.pathname)
    throw Error('Unexpected Microsoft redirect URL.');
  const p = callback.searchParams;
  if (p.get('error')) throw Error(p.get('error_description') || p.get('error'));
  if (p.get('state') !== state) throw Error('OAuth state mismatch');
  if (!p.get('code')) throw Error('No authorization code returned');
  const j = await tokenRequest(authority, {
    client_id: c.client, grant_type: 'authorization_code', code: p.get('code'),
    redirect_uri: redirect, code_verifier: verifier, scope: SCOPE
  });
  const tenant = await validateMicrosoftIdentity(j.id_token, c.client, loginNonce);
  await saveTokens(j, {tenant, client:c.client, identityVersion:1});
  await log('info', 'Microsoft Outlook account connected');
  return 'Microsoft connected';
}

async function getAccess() {
  const c = await effectiveConfig();
  const stored = await G(['tokens']);
  if (!validStoredIdentity(stored.tokens)) {
    await S.remove('access');
    await put({tokens:{refresh:null},verifiedAddress:'',verifiedAt:0});
    throw Error('Microsoft session needs renewal. Sign in again to verify your organization.');
  }
  const { access } = await S.get('access');
  if (access?.token && access.expiresAt > Date.now() + 60000) return access.token;

  const { tokens } = await G(['tokens']);
  if (tokens?.refresh && guid(c.client) && guid(c.tenant)) {
    try {
      const j = await tokenRequest(tokens.tenant, {
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

async function verifyOutlook() {
  const token = await getAccess();
  const response = await fetch('https://graph.microsoft.com/v1.0/me?$select=mail,userPrincipalName', {
    headers: { Authorization: 'Bearer ' + token }
  });
  if (!response.ok) throw Error('Microsoft account check failed (HTTP ' + response.status + '). Reconnect Outlook.');
  const me = await response.json();
  const address = me.mail || me.userPrincipalName || '';
  if (!address.includes('@')) throw Error('Connected Outlook account has no usable email address.');
  await put({ verifiedAddress: address, verifiedAt: Date.now() });
  return { address };
}

// ---------------------------------------------------------------------------
// Grafana tab handling and capture
// ---------------------------------------------------------------------------
// Returns the tab showing the CONFIGURED dashboard. Never picks some other Grafana dashboard.
async function getDashboardTab(c) {
  const {tabId} = await G(['tabId']);
  if(tabId) {
    const t=await chrome.tabs.get(tabId).catch(()=>null);
    if(t && isDashboardTab(t.url,c.dashboard))return {tab:t,created:false};
    if(t)throw Error('The linked tab changed its dashboard, time or filters. Open the required Grafana dashboard and click Use tab again. No replacement tab was captured.');
  }
  const tabs=await chrome.tabs.query({url:`https://${GRAFANA_HOST}/*`});
  const t=tabs.find(x=>isDashboardTab(x.url,c.dashboard));
  if(t)return {tab:t,created:false};
  throw Error('Open the required Grafana dashboard in Chrome and select Use tab. This version captures the linked tab only; it never silently opens a different layout.');
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

async function screenshot(c) {
  await progress('Finding linked Grafana tab', 15);
  const {tab}=await getDashboardTab(c);
  await put({tabId:tab.id});
  if(tab.discarded)throw Error('Chrome discarded the Grafana tab. Open it and wait for the graphs, then retry.');
  if(tab.status!=='complete')await waitLoaded(tab.id,45000);
  return await captureDashboardTiles(tab.id,c);
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
  const {to, cc, bcc} = parseRecipients(c, permittedDomains);
  const recipients = { toRecipients: to, ccRecipients: cc, bccRecipients: bcc };
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
  // Revalidate AFTER token renewal and sender checks, immediately before POST.
  const latest = await effectiveConfig();
  if (captureSignature(latest) !== captureSignature(c) ||
      JSON.stringify(parseRecipients(latest)) !== JSON.stringify(parseRecipients(c)))
    throw Error('Report settings changed during capture. Review them and retry; no email was sent.');
  await requireApprovedPreview(c);
  if (!test && (await G(['mode'])).mode !== 'running')
    throw cancelledError();
  assertRunActive();
  await put({ submissionPending: true });
  if (currentRun) currentRun.submissionPrepared = true;
  assertRunActive();
  let r;
  try { r = await fetch('https://graph.microsoft.com/v1.0/me/sendMail', {
    method: 'POST', signal: AbortSignal.timeout(30000),
    headers: { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' },
    body: JSON.stringify(msg)
  }); } catch(e) { throw Error('Outlook acceptance is unconfirmed (network/timeout). Check Sent Items before retrying to avoid duplicates. '+e.message); }
  if (r.status !== 202) {
    await put({ submissionPending: false });
    let reason = await r.text();
    try { reason = JSON.parse(reason).error?.message || reason; } catch { /* keep raw text */ }
    throw Error('Graph ' + r.status + ': ' + reason.slice(0, 280));
  }
  return { name, to: recipients.toRecipients.length, cc: recipients.ccRecipients.length, bcc: recipients.bccRecipients.length };
}

let busy = false;
let currentRun = null;
function cancelledError() {
  const e = Error('Report cancelled before submission. No email was sent.');
  e.code = 'REPORT_CANCELLED';
  return e;
}
function assertRunActive() {
  if (currentRun?.cancelled) throw cancelledError();
}
async function progress(stage, percent) {
  if (!currentRun) return;
  assertRunActive();
  currentRun = { ...currentRun, stage, percent };
  const state = { ...currentRun, busy: true, updatedAt: Date.now() };
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
  // Email attempts (not screenshot previews) have their own durable outcome.
  // "accepted" means Graph HTTP success, NOT recipient delivery confirmation.
  // A Chrome extension API call during long panel waits prevents the normal
  // service-worker idle cutoff. Chrome may still suspend/discard background tabs.
  const keepAlive = setInterval(() => chrome.runtime.getPlatformInfo().catch(() => {}), 20000);
  try {
    if (!captureOnly) await put({ lastMailAttemptAt: currentRun.startedAt,
      lastMailKind: currentRun.kind, lastMailOutcome: 'working', lastMailError: '' });
    await progress('Checking configuration', 5);
    const c = await effectiveConfig();
    captureOnly ? checkCaptureConfig(c) : checkConfig(c);
    if(!captureOnly)await requireApprovedPreview(c);
    await put({ lastError: '' });
    const shot = await screenshot(c);
    assertRunActive();
    await put({ lastCaptureAt: Date.now(), lastCaptureUrl: c.dashboard, lastCaptureMeta: shot.meta, lastCaptureSignature: captureSignature(c) });
    if (captureOnly) {
      await put({ capturePreview: `data:${shot.mime};base64,${shot.data}`, capturePreviewMeta: shot.meta,
        capturePreviewSignature: captureSignature(c), capturePreviewId: crypto.randomUUID() });
      await finishProgress('Preview ready', true);
      await log('info', 'Grafana screenshot preview captured successfully');
      // The popup may close during a long capture. The worker owns this action.
      try { await chrome.tabs.create({ url: chrome.runtime.getURL('preview.html') }); }
      catch (e) { await log('warn', 'Preview saved. Use View preview to open it: ' + e.message); }
      await notify('Screenshot ready to review', 'Open Smart Report and review the preview. Approve it before sending reports.');
      return { previewReady: true, meta: shot.meta };
    }
    if (!test && (await G(['mode'])).mode !== 'running') throw cancelledError();
    await put({ lastMailOutcome:'submitting' });
    await progress('Submitting email to Outlook', 90);
    const res = await email(c, shot, test);
    const stats = await G(['sent', 'sentTest', 'sentScheduled']);
    await put({ sent: (stats.sent || 0) + 1,
      [test ? 'sentTest' : 'sentScheduled']: ((test ? stats.sentTest : stats.sentScheduled) || 0) + 1,
      lastSent: new Date().toISOString(), lastMailOutcome: 'accepted', lastMailError: '', submissionPending: false,
      lastCompletedMail: { at:Date.now(), kind:currentRun.kind, outcome:'accepted' },
      lastMailRecipientCount: res.to + res.cc + res.bcc,
      lastStatus: 'Microsoft Graph accepted email for processing (not confirmed delivered)',
      lastError: '', consecutiveFailures: 0 });
    await finishProgress('Email accepted by Outlook', true);
    if (test) await notify('Test accepted by Outlook', 'Check the received attachment before starting automatic reports. Acceptance does not confirm delivery.');
    await log('success', `${test ? 'Test' : 'Scheduled'} email accepted by Graph; recipients ${res.to + res.cc + res.bcc}. Delivery not confirmed.`);
    return { message: 'Microsoft accepted this email for processing. Check Outlook Sent Items and recipient inbox to verify delivery.' };
  } catch (e) {
    if (e.code === 'REPORT_CANCELLED') {
      await put({ ...(currentRun?.submissionPrepared ? { submissionPending: false } : {}), lastStatus: e.message, lastError: '',
        ...(!captureOnly ? { lastMailOutcome: 'cancelled', lastMailError: '' } : {}) });
      await finishProgress('Report cancelled', false);
      await log('info', e.message);
      throw e;
    }
    // A worker/storage failure after POST is also uncertain until reconciled.
    if (currentRun?.submissionPrepared && (await G(['submissionPending'])).submissionPending &&
        !/acceptance is unconfirmed/.test(e.message))
      e = Error('Outlook acceptance is unconfirmed. Check Sent Items before retrying. ' + e.message);
    if (/acceptance is unconfirmed/.test(e.message)) await schedule('paused');
    const failedStage=(await G(['runState'])).runState?.stage || 'Starting report';
    if (!captureOnly) {
      const stats = await G(['failedMail', 'failedTest', 'failedScheduled']);
      await put({
        failedMail: (stats.failedMail || 0) + 1,
        [test ? 'failedTest' : 'failedScheduled']: ((test ? stats.failedTest : stats.failedScheduled) || 0) + 1,
        lastMailOutcome: 'failed', lastMailError: e.message,
        lastMailFailAt: new Date().toISOString(), lastCompletedMail: { at:Date.now(), kind:currentRun.kind, outcome:'failed', error:e.message }
      });
    }
    await put({ lastError: e.message, lastStatus: (captureOnly ? 'Screenshot failed: ' : 'Email not sent: ') + e.message });
    await finishProgress(captureOnly ? 'Screenshot failed' : 'Email not sent', false, e.message);
    if (test || captureOnly) await notify(captureOnly ? 'Screenshot needs attention' : 'Test email needs attention', 'Open Smart Report for the error and next steps.');
    await log('error', '[' + (currentRun?.kind || 'run') + ' / ' + failedStage + '] ' + e.message + (e.stack ? '\n' + e.stack.slice(0, 800) : ''));
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
let scheduleQueue = Promise.resolve();
function schedule(mode) {
  // Stop the in-flight report immediately, then serialize alarm changes so a
  // slow Start cannot overwrite a subsequent Pause/Stop.
  if (mode !== 'running' && currentRun) currentRun.cancelled = true;
  scheduleQueue = scheduleQueue.catch(() => {}).then(() => applySchedule(mode));
  return scheduleQueue;
}
async function applySchedule(mode) {
  if (mode === 'running') {
    if (busy) throw Error('Wait for the current report to finish before starting or resuming.');
    const c = await effectiveConfig();
    checkConfig(c);
    await requireApprovedPreview(c);
    if (!(await G(['tokens'])).tokens?.refresh) throw Error('Connect Outlook before starting monitoring.');
    await chrome.alarms.clear(ALARM);
    await chrome.alarms.create(ALARM, { periodInMinutes: +c.interval, delayInMinutes: +c.interval });
    await put({ consecutiveFailures: 0 });
  } else {
    if (currentRun) currentRun.cancelled = true;
    await chrome.alarms.clear(ALARM); // pausing/stopping never depends on the config being valid
  }
  await put({ mode, lastStatus: mode === 'running' ? 'Monitoring started' : 'Monitoring ' + mode });
  await log('info', 'Monitoring ' + mode);
  return mode;
}

// Alarms can be cleared by an extension update/reload or a browser restart: put it back if we should be running.
async function restoreAlarmOnce() {
  // First v3.4 load is a deliberate safe reset: old versions may have been
  // scheduling failed runs with invalid settings. Require an explicit test
  // before re-enabling reports, while preserving dashboard and email settings.
  const installed = await G(['smartReportVersion', 'mode', 'submissionPending']);
  if (installed.submissionPending) {
    await chrome.alarms.clear(ALARM);
    await put({ mode: 'paused', runState: null, lastMailOutcome: 'failed',
      lastMailError: 'Previous email acceptance is unconfirmed. Check Sent Items before retrying.',
      lastError: 'Previous email acceptance is unconfirmed. Check Sent Items before retrying.' });
    return;
  }
  if (installed.smartReportVersion !== '3.7.5') {
    await chrome.alarms.clear(ALARM);
    await put({ smartReportVersion: '3.7.5', upgradedAt: Date.now(),
      mode: installed.mode === 'running' ? 'paused' : (installed.mode || 'stopped'),
      runState: null, lastError: '', lastMailError: '', lastMailOutcome:'', consecutiveFailures: 0,
      approvedCaptureSignature:'', capturePreview:null, capturePreviewSignature:'', capturePreviewId:'',
      lastStatus: 'Updated to v3.7.5. Check screenshot and approve its layout before emailing.' });
    await log('info', 'Smart Report v3.7.5 installed; old monitoring paused until tested');
    return;
  }
  const { mode } = await G(['mode']);
  if (mode !== 'running') return;
  const c = await effectiveConfig();
  try {
    checkConfig(c);
    await requireApprovedPreview(c);
    if (!(await G(['tokens'])).tokens?.refresh) throw Error('Reconnect Outlook before resuming reports.');
  } catch (e) {
    await chrome.alarms.clear(ALARM);
    await put({mode:'paused',lastError:e.message,lastStatus:'Schedule paused: '+e.message});
    return;
  }
  const m = Number(c.interval);
  const existing = await chrome.alarms.get(ALARM);
  if (existing && existing.periodInMinutes === m) return;
  await chrome.alarms.clear(ALARM);
  await chrome.alarms.create(ALARM, { periodInMinutes: m, delayInMinutes: m });
  await log('info', 'Schedule restored after extension or browser restart');
}

let restoreFlight=null;
function restoreAlarm(){return restoreFlight||(restoreFlight=restoreAlarmOnce().finally(()=>restoreFlight=null));}

chrome.alarms.onAlarm.addListener(async a => {
  if (a.name !== ALARM) return;
  const { mode } = await G(['mode']);
  if (mode !== 'running') return;
  try {
    await run(false, false);
  } catch (e) {
    if (e.code === 'REPORT_CANCELLED') return;
    if (/acceptance is unconfirmed/.test(e.message)) { await schedule('paused'); await notify('Check Outlook Sent Items', 'Email acceptance is unconfirmed. Reports paused to avoid duplicate retries.'); return; }
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
      await notify('Smart Report: email not sent', (n > 1 ? n + ' consecutive failures. ' : '') + String(e.message).slice(0, 150));
  }
});

chrome.runtime.onStartup.addListener(() => restoreAlarm().catch(e => log('error', 'Schedule restore failed: ' + e.message)));
chrome.runtime.onInstalled.addListener(() => restoreAlarm().catch(e => log('error', 'Schedule restore failed: ' + e.message)));
restoreAlarm().catch(e => log('error', 'Schedule restore failed: ' + e.message));

// ---------------------------------------------------------------------------
// Messages from the popup
// ---------------------------------------------------------------------------
const CONFIG_KEYS = ['dashboard', 'to', 'interval', 'expandRows'];

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  // Only our own extension pages may drive the worker.
  if (sender.id !== chrome.runtime.id || (sender.url && !sender.url.startsWith(chrome.runtime.getURL('')))) {
    reply({ ok: false, error: 'Unauthorized sender' });
    return false;
  }
  (async () => {
    await restoreFlight;
    switch (msg.action) {
      case 'GET': {
        const d = await G(['config', 'mode', 'sent', 'sentTest', 'sentScheduled', 'failedMail', 'failedTest', 'failedScheduled', 'lastMailAttemptAt', 'lastMailKind', 'lastMailOutcome', 'lastMailError', 'lastMailRecipientCount', 'lastMailFailAt', 'lastSent', 'lastStatus', 'lastError', 'tokens', 'consecutiveFailures', 'runState', 'logs', 'verifiedAddress', 'verifiedAt', 'lastCaptureAt', 'lastCaptureUrl', 'upgradedAt', 'lastCaptureMeta', 'lastCaptureSignature', 'approvedCaptureSignature', 'lastCompletedMail']);
        const a = await chrome.alarms.get(ALARM);
        return {
          config: await effectiveConfig(), mode: d.mode, sent: d.sent || 0, failedMail: d.failedMail || 0,
          sentTest: d.sentTest || 0, sentScheduled: d.sentScheduled || 0,
          failedTest: d.failedTest || 0, failedScheduled: d.failedScheduled || 0,
          lastMailAttemptAt: d.lastMailAttemptAt || 0, lastMailKind: d.lastMailKind || '',
          lastMailOutcome: d.lastMailOutcome || '', lastMailError: d.lastMailError || '',
          lastMailRecipientCount: d.lastMailRecipientCount || 0,
          lastSent: d.lastSent, lastStatus: d.lastStatus, lastError: d.lastError,
          consecutiveFailures: d.consecutiveFailures || 0,
          companyConfigured: guid(COMPANY_MICROSOFT.clientId) && guid(COMPANY_MICROSOFT.tenantId),
          connected: !!d.tokens?.refresh && validStoredIdentity(d.tokens), verifiedAddress: d.verifiedAddress || '', verifiedAt: d.verifiedAt || 0, lastCaptureAt: d.lastCaptureAt || 0, lastCaptureUrl: d.lastCaptureUrl || '',
          lastCaptureMeta: d.lastCaptureMeta || null, lastCompletedMail: d.lastCompletedMail || null,
          approvedPreview: !!d.approvedCaptureSignature && !!d.config?.dashboard && d.approvedCaptureSignature===safeCaptureSignature(await effectiveConfig()),
          allowedDomains: ALLOWED_DOMAINS,
          grafanaDefaults: { from: DEFAULT_GRAFANA_FROM, to: DEFAULT_GRAFANA_TO, refresh: DEFAULT_GRAFANA_REFRESH, captureFullPage:true, reloadBeforeCapture:false },
          senderDomainOnly: !ALLOWED_DOMAINS.length,
          events: (d.logs || []).filter(e => !d.upgradedAt || Date.parse(e.at) >= d.upgradedAt).slice(-3).reverse(),
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
        if (typeof updated.dashboard === 'string' && updated.dashboard.trim()) {
          try { updated.dashboard = checkUrl(updated.dashboard.trim()); } catch { /* keep draft text until user tests */ }
        }
        updated.settle = DEFAULT_PANEL_DELAY;
        updated.cc = ''; updated.bcc = '';
        if (guid(COMPANY_MICROSOFT.clientId)) updated.client = COMPANY_MICROSOFT.clientId;
        if (guid(COMPANY_MICROSOFT.tenantId)) updated.tenant = COMPANY_MICROSOFT.tenantId;
        // Allow autosaving partial drafts; full checks happen only for Send/Start.
        const captureChanged = safeCaptureSignature(updated) !== safeCaptureSignature(old.config || {});
        if (currentRun && (captureChanged || updated.to !== old.config?.to)) currentRun.cancelled = true;
        await put({ config: updated });
        if(captureChanged){
          await put({ approvedCaptureSignature:'', lastCaptureSignature:'' });
          if((await G(['mode'])).mode==='running')await schedule('paused');
        }
        if ((await G(['mode'])).mode === 'running' && String(old.config?.interval) !== String(updated.interval)) {
          const interval = Number(updated.interval);
          if (Number.isInteger(interval) && interval >= 1 && interval <= 1440) {
            await chrome.alarms.clear(ALARM);
            await chrome.alarms.create(ALARM, { periodInMinutes: interval, delayInMinutes: interval });
            await put({ lastStatus: 'Schedule updated to every ' + interval + ' minutes' });
            await log('info', 'Schedule updated: every ' + interval + ' minutes');
          } else {
            await schedule('paused');
            await put({lastError:'Enter an interval from 1 to 1440 minutes, then resume automatic emails.'});
          }
        }
        return { ok: true };
      }
      case 'APPROVE_CAPTURE': {
        if (busy) throw Error('Wait for the current report to finish before approving a preview.');
        const c=await effectiveConfig(), d=await G(['capturePreviewSignature','capturePreview','capturePreviewId']);
        if (!msg.previewId || msg.previewId !== d.capturePreviewId)
          throw Error('This preview has been replaced. Open View preview and review the latest screenshot.');
        if(!d.capturePreview || d.capturePreviewSignature!==captureSignature(c))throw Error('Dashboard settings changed. Capture a new preview before approving.');
        await put({approvedCaptureSignature:d.capturePreviewSignature,lastStatus:'Screenshot layout approved. Send one test email next.'});
        await log('info','Screenshot layout approved by user');
        return {approved:true};
      }
      case 'PREVIEW_DATA': {
        const d=await G(['capturePreview','capturePreviewMeta','capturePreviewSignature','approvedCaptureSignature','capturePreviewId']);
        return {image:d.capturePreview,meta:d.capturePreviewMeta,previewId:d.capturePreviewId,approved:!!d.capturePreviewSignature&&d.capturePreviewSignature===d.approvedCaptureSignature};
      }
      case 'LOGIN': { await auth(true); return await verifyOutlook(); }
      case 'VERIFY': return await verifyOutlook();
      case 'LOGOUT': {
        await schedule('paused');
        await S.remove('access');
        await put({ tokens: { refresh: null }, verifiedAddress: '', verifiedAt: 0 });
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
        if (busy) throw Error('Wait for the current report to finish before linking another tab.');
        if (!Number.isInteger(msg.tabId)) throw Error('Open the Grafana dashboard tab, click the extension icon from that tab, then try again.');
        const tab = await chrome.tabs.get(msg.tabId);
        const url = checkUrl(tab.url || msg.url);
        const original=new URL(tab.url||msg.url);
        if(['from','to','refresh'].some(k=>!original.searchParams.has(k))) {
          await chrome.tabs.update(msg.tabId,{url}); // one-time defaults application, not a recurring reload
        }
        if ((await G(['mode'])).mode === 'running') await schedule('paused');
        await put({ tabId: msg.tabId, approvedCaptureSignature:'', capturePreviewSignature:'', capturePreviewId:'' });
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

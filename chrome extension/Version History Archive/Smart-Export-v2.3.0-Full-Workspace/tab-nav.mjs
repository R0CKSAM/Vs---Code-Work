// Smart Export internal navigation. Only extension and approved Grafana tabs.
const GRAFANA_HOST='grafana-apj.trafficpeak.live';
const WORKSPACE_URL=chrome.runtime.getURL('workspace.html');
function isGrafanaDashboard(url){try{const u=new URL(url);return u.protocol==='https:'&&u.hostname===GRAFANA_HOST&&u.pathname.startsWith('/d/');}catch{return false;}}
export async function openWorkspace(){
 const existing=(await chrome.tabs.query({})).filter(tab=>tab.url===WORKSPACE_URL);
 if(existing.length){const t=existing[0];await chrome.tabs.update(t.id,{active:true});if(t.windowId!=null)await chrome.windows.update(t.windowId,{focused:true});return t;}
 return await chrome.tabs.create({url:WORKSPACE_URL,active:true});
}
export async function findGrafanaTab(){
 const {smartExportReturnGrafanaTabId:preferred,smartExportConfig:config}=await chrome.storage.local.get(['smartExportReturnGrafanaTabId','smartExportConfig']);
 if(Number.isInteger(preferred)){
   try{const t=await chrome.tabs.get(preferred);if(isGrafanaDashboard(t.url))return t;}catch{}
 }
 const tabs=(await chrome.tabs.query({url:`https://${GRAFANA_HOST}/*`})).filter(t=>isGrafanaDashboard(t.url));
 if(tabs.length){const saved=config?.dashboardUrl;return tabs.find(t=>t.url===saved)||tabs.find(t=>t.active)||tabs[0];}
 return null;
}
export async function returnToGrafana(){
 let t=await findGrafanaTab();
 if(t){await chrome.tabs.update(t.id,{active:true});if(t.windowId!=null)await chrome.windows.update(t.windowId,{focused:true});return t;}
 const r=await chrome.storage.local.get('smartExportConfig');const saved=r.smartExportConfig?.dashboardUrl;
 const url=isGrafanaDashboard(saved)?saved:`https://${GRAFANA_HOST}/`;
 return await chrome.tabs.create({url,active:true});
}
export async function rememberGrafanaTabIfActive(){
 const [tab]=await chrome.tabs.query({active:true,lastFocusedWindow:true});
 if(tab?.id && isGrafanaDashboard(tab.url))await chrome.storage.local.set({smartExportReturnGrafanaTabId:tab.id});
 return tab;
}

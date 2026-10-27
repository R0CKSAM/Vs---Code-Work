import assert from 'node:assert/strict';
const ROOT='chrome-extension://test-id/workspace.html';
const GRAFANA='https://grafana-apj.trafficpeak.live/d/db7ce6f6-d689-4976-89e5-ddf0b5401f97/analytics?orgId=743';
const state={tabs:[{id:1,url:GRAFANA,active:true,windowId:12},{id:2,url:'https://example.com/',active:false,windowId:12}],storage:{smartExportConfig:{dashboardUrl:GRAFANA}}};
const calls={create:0,update:0,focus:0};
const tabs={
  query:async ({url,active}={})=>{
    if(active===true)return state.tabs.filter(t=>t.active);
    if(url&&url.includes('grafana-apj.trafficpeak.live'))return state.tabs.filter(t=>t.url?.startsWith('https://grafana-apj.trafficpeak.live/'));
    return state.tabs;
  },
  get:async id=>{const t=state.tabs.find(x=>x.id===id);if(!t)throw new Error('Tab missing');return t;},
  create:async ({url,active})=>{calls.create++;const t={id:state.tabs.length+1,url,active,windowId:12};state.tabs.push(t);return t;},
  update:async (id,props)=>{calls.update++;const t=state.tabs.find(x=>x.id===id);Object.assign(t,props);return t;}
};
globalThis.chrome={runtime:{getURL:p=>'chrome-extension://test-id/'+p},tabs,windows:{update:async()=>{calls.focus++;}},storage:{local:{get:async keys=>Object.fromEntries((Array.isArray(keys)?keys:[keys]).map(k=>[k,state.storage[k]])),set:async obj=>Object.assign(state.storage,obj)}}};
const nav=await import('../tab-nav.mjs');
assert.equal((await nav.rememberGrafanaTabIfActive()).id,1);
assert.equal(state.storage.smartExportReturnGrafanaTabId,1);
const first=await nav.openWorkspace();
assert.equal(first.url,ROOT);assert.equal(calls.create,1);
const second=await nav.openWorkspace();
assert.equal(second.id,first.id);assert.equal(calls.create,1,'Must reuse existing workspace tab');
const graf=await nav.returnToGrafana();
assert.equal(graf.id,1);assert.equal(calls.create,1,'Must reuse existing Grafana tab');
state.tabs=state.tabs.filter(x=>x.id!==1);delete state.storage.smartExportReturnGrafanaTabId;
const opened=await nav.returnToGrafana();assert.equal(opened.url,GRAFANA,'Back to Grafana opens saved dashboard after tab closes');
console.log('PASS: Launcher single workspace, preferred Grafana tab, and saved fallback');

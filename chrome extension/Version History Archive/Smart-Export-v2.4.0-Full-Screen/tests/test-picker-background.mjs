import assert from 'node:assert/strict';
import {DEFAULT_DASHBOARD_URL} from '../core.mjs';
const local={};let handler=null;
globalThis.chrome={
 storage:{local:{get:async defaults=>({...defaults,...local}),set:async patch=>Object.assign(local,patch)}},
 runtime:{onMessage:{addListener:f=>{handler=f}},onInstalled:{addListener:()=>{}},onStartup:{addListener:()=>{}}},
 tabs:{query:async()=>[]},
 alarms:{onAlarm:{addListener:()=>{}},get:async()=>({name:'smartExportDailyCheck'}),create:async()=>{}},
 action:{setBadgeText:async()=>{},setBadgeBackgroundColor:async()=>{}},
 scripting:{executeScript:async()=>[]}
};
await import('../background.mjs');
assert(handler);
const request=(type,options={})=>new Promise(resolve=>handler({type,...options},{},resolve));
let count=0;const test=(label,cond)=>{assert(cond,label);count++;console.log('PASS',label);};
const saved=await request('SAVE_PICKER',{dashboardUrl:DEFAULT_DASHBOARD_URL,reports:['geo','kpis']});
test('Save user report categories',saved.ok===true&&saved.data.config.selectedReport==='executive');
const started=await request('ENABLE_PICKED',{enabled:true,reports:['geo','kpis']});
test('Schedule selected categories',started.ok===true&&started.data.config.autoReport==='picked'&&started.data.config.enabled===true&&started.data.config.autoReports.length===2);
const same=await request('SAVE_PICKER',{dashboardUrl:DEFAULT_DASHBOARD_URL,reports:['kpis','geo']});
test('Editing without category changes keeps schedule',same.ok===true&&same.data.config.enabled===true);
const different=await request('SAVE_PICKER',{dashboardUrl:DEFAULT_DASHBOARD_URL,reports:['channel']});
test('Changing selected categories pauses old schedule',different.ok===true&&different.data.config.enabled===false);
const malformed=await request('ENABLE_PICKED',{enabled:true,reports:['geo','geo']});
test('Duplicate categories not accepted',malformed.ok===false);
const empty=await request('SYNC_PICKED',{from:'2026-10-01',to:'2026-10-02',reports:[]});
test('Empty query selection not executed',empty.ok===false);
const noTab=await request('SYNC_PICKED',{from:'2026-10-01',to:'2026-10-02',reports:['geo']});
test('Missing Grafana login/tab returns safe error',noTab.ok===false && /Open your saved Grafana/.test(noTab.error));
console.log(`PASSED ${count} background command tests`);

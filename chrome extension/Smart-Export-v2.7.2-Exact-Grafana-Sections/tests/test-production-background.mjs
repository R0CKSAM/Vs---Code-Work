import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {fileURLToPath} from 'node:url';
import {ALL_REPORT_ORDER,parseReportFrames} from '../reports.mjs';
import {DEFAULT_DASHBOARD_URL} from '../core.mjs';
import {parseDashboardUrl} from '../core.mjs';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const state={local:{smartExportConfig:{dashboardUrl:DEFAULT_DASHBOARD_URL,enabled:false}},queries:0,commits:[],targets:[],failKey:null,queryFailure:null,changedSource:false,gate:null,now:Date.parse('2026-10-27T04:00:00Z')};
let listener;
let tabs=[{id:1,url:DEFAULT_DASHBOARD_URL,active:true}];
class Clock extends Date{constructor(...args){super(...(args.length?args:[state.now]));}static now(){return state.now;}}
const ctx=vm.createContext({console,URL,Date:Clock,setTimeout,clearTimeout,AbortSignal,structuredClone,
 location:{origin:'https://grafana-apj.trafficpeak.live',pathname:'/d/db7ce6f6-d689-4976-89e5-ddf0b5401f97/sessions'},
 TEST:state,
 chrome:{
  runtime:{onMessage:{addListener:fn=>listener=fn},onInstalled:{addListener(){}},onStartup:{addListener(){}}},
  alarms:{onAlarm:{addListener(){}},get:async()=>({}),create:async()=>{}},
  action:{setBadgeText:async()=>{if(state.failBadge)throw new Error('Badge failure');},setBadgeBackgroundColor:async()=>{}},
  storage:{local:{get:async defaults=>({...defaults,...state.local}),set:async patch=>{
   if(state.failKey&&Object.hasOwn(patch,state.failKey)){state.failKey=null;throw new Error('Synthetic storage failure');}
   Object.assign(state.local,structuredClone(patch));
  }}},tabs:{query:async()=>tabs},
  scripting:{executeScript:async request=>{state.targets.push(request.target.tabId);return [{result:await request.func(...request.args)}];}}
 },
 DB:{read:async()=>Object.fromEntries(ALL_REPORT_ORDER.map(id=>[id,[]])),put:async(key,from,to,rows)=>{state.commits.push(structuredClone(rows));if(state.failAfterCommit)state.failKey='smartExportConfig';return Object.values(rows).reduce((n,r)=>n+r.length,0);}},
 fetch:async(url,options={})=>{
  assert.equal(options.headers?.['X-Grafana-Org-Id'],'743');
  assert(options.signal,'Every Grafana request must have a timeout signal');
  if(url.startsWith('/api/dashboards/'))return {ok:true,json:async()=>({dashboard:{panels:[{id:20,title:'Playtime by GEO',targets:[{datasource:{uid:'fixture-source'},rawSql:state.changedSource?'SELECT 1':'count() * 6 / 60.0 decodeURLComponent(country)'}]}]}})};
  state.queries++;
  if(state.gate)await state.gate;
  if(state.queryFailure==='timeout'){const error=new Error('Timeout');error.name='TimeoutError';throw error;}
  if(state.queryFailure==='html')return {ok:true,json:async()=>{throw new Error('HTML');}};
  if(state.queryFailure==='401')return {ok:false,status:401,json:async()=>({message:'Sign in again'})};
  const date=new Date(Number(JSON.parse(options.body).from)+19800000).toISOString().slice(0,10);
  return {ok:true,json:async()=>({results:{A:{frames:[{schema:{fields:['report_date','country','state','city','playtime_minutes'].map(name=>({name}))},data:{values:[[date],['IN'],['Delhi'],[null],[12]]}}]}}})};
 }
});
const cache=new Map();
async function moduleFor(name){
 if(cache.has(name))return cache.get(name);
 const source=name==='report-db.mjs'?'export const putReportsAtomically=(...args)=>DB.put(...args);export const allReportRows=(...args)=>DB.read(...args);export const clearReportRows=async()=>{};':name==='database.mjs'?'export const replaceRange=async()=>{};export const readDataset=async()=>[];export const clearDataset=async()=>{};':fs.readFileSync(path.join(root,name),'utf8')+(name==='background.mjs'?'\nexport {automaticCheck};':'');
 const mod=new vm.SourceTextModule(source,{context:ctx,identifier:name});cache.set(name,mod);
 await mod.link(specifier=>moduleFor(path.basename(specifier)));return mod;
}
const background=await moduleFor('background.mjs');await background.evaluate();
const request=(type,options={})=>new Promise(resolve=>listener({type,...options},{},resolve));
const sync=()=>request('SYNC_PICKED',{from:'2026-10-20',to:'2026-10-20',reports:['geo']});
let checks=0;
const check=(ok,message)=>{assert(ok,message);checks++;};
let response=await sync();check(response.ok&&state.commits.length===1,'Successful query must commit');
check(state.commits[0].geo[0].city==='','Missing city must be retained');
state.failKey='smartExportActivity';response=await sync();check(!response.ok&&response.error.includes('storage'),'Activity write failure must be returned');
response=await sync();check(response.ok,'Storage error must release the running lock');
state.changedSource=true;let before=state.queries;response=await sync();check(!response.ok&&state.queries===before,'Source validation must occur before querying');state.changedSource=false;
tabs=[{id:1,url:DEFAULT_DASHBOARD_URL.replace('orgId=743','orgId=999'),active:true},{id:2,url:DEFAULT_DASHBOARD_URL,active:false}];
response=await sync();check(response.ok&&state.targets.at(-1)===2,'Correct organization tab must be selected');
for(const failure of ['401','html','timeout']){state.queryFailure=failure;const count=state.commits.length;response=await sync();check(!response.ok&&state.commits.length===count,`${failure}: old data must be preserved`);}
state.queryFailure=null;state.failAfterCommit=true;response=await sync();check(response.ok&&response.data.warning.includes('were saved'),'Metadata failure after commit must not falsely report lost data');state.failAfterCommit=false;
state.failBadge=true;response=await sync();check(response.ok,'Badge failure must not invalidate saved reports');state.failBadge=false;
let release;state.gate=new Promise(resolve=>release=resolve);before=state.queries;const pending=sync();
while(state.queries===before)await new Promise(resolve=>setTimeout(resolve,1));
response=await sync();check(!response.ok&&response.error.includes('already running'),'Concurrent fetch must be blocked');
response=await request('SAVE_PICKER',{dashboardUrl:DEFAULT_DASHBOARD_URL,reports:['geo']});check(!response.ok,'Source mutation must be blocked during a query');
response=await request('ENABLE',{enabled:false});check(response.ok,'Pause must remain possible during a query');
release();state.gate=null;check((await pending).ok&&!state.local.smartExportConfig.enabled,'Finishing a query must not re-enable a paused schedule');
Object.assign(state.local.smartExportConfig,{enabled:true,v2Mode:true,autoReport:'picked',autoReports:['geo'],v2LastAutoDates:{},scheduleHourIST:8,autoRefreshDays:3});
before=state.queries;state.now=Date.parse('2026-10-27T01:00:00Z');await background.namespace.automaticCheck();check(state.queries===before,'Daily job must wait until configured IST hour');
state.now=Date.parse('2026-10-27T04:00:00Z');await background.namespace.automaticCheck();check(state.queries===before+1,'Due daily job must run');
check(Object.values(state.local.smartExportConfig.v2LastAutoDates).includes('2026-10-26'),'Daily completion marker must be recorded');
await background.namespace.automaticCheck();check(state.queries===before+1,'Completed daily job must not run twice');
const diag={};const nullable={results:{A:{frames:[{schema:{fields:['report_date','country','state','city','playtime_minutes'].map(name=>({name}))},data:{values:[['2026-10-20'],['IN'],[null],[null],[null]]}}]}}};
check(parseReportFrames(nullable,'geo','2026-10-20','2026-10-20',diag)[0].playtime_minutes===null&&diag.missingValues===1,'Missing metric must remain null, not become zero');
check(parseDashboardUrl(DEFAULT_DASHBOARD_URL+'&var-hdx_query_errors=previous-timeout').orgId==='743','Hydrolix diagnostic metadata must not be mistaken for a data filter');
console.log(`PASS ${checks} production background checks: actual injected requests, storage failures, source validation, locks and daily scheduling`);

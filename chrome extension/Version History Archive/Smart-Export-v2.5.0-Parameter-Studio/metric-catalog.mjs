/* Smart Picker field dictionary. Only validated fields from the fixed v2 Grafana reports.
 * A dimension is compulsory for its dataset; arbitrary cross-grain joins are not allowed. */
import {REPORT_ORDER,REPORTS,REPORT_COLUMNS} from './reports.mjs';
export const GROUPS={
 kpis:{title:'Audience & overview',short:'Who watched and how much?',section:'Session and Users Stats',grain:'One row per day',icon:'👥',tone:'audience'},
 channel:{title:'Channels',short:'Which channels are most watched?',section:'Viewership Trend · Playtime by Channel',grain:'Date + channel',icon:'▣',tone:'channel'},
 geo:{title:'Locations',short:'Where is playtime coming from?',section:'Playtime by GEO',grain:'Date + country + state + city',icon:'◎',tone:'location'},
 devices:{title:'Devices & operating systems',short:'What devices does your audience use?',section:'Total Device ID by Platform / OS',grain:'Date + platform + OS',icon:'▤',tone:'devices'},
 content:{title:'Content & shows',short:'What content attracts viewers?',section:'Popular Content',grain:'Date + title',icon:'▷',tone:'content'},
 traffic:{title:'Traffic & streaming',short:'When are your peaks?',section:'Time Series · Viewership Trend',grain:'Date + hour',icon:'⌁',tone:'traffic'}
};
export const DETAILS={
 unique_devices:{label:'Unique device IDs',help:'Distinct device identifiers within each selected day or group. Not the count of individual people.'},
 unique_ips:{label:'Unique IP addresses',help:'Distinct IP addresses within each date/group. Shared connections and IP changes can affect this measure.'},
 session_ids:{label:'Distinct session IDs',help:'Unique session identifiers within each date/group.'},
 ip_ua_sessions:{label:'IP + browser/device sessions',help:'Unique combinations of IP address and User Agent.'},
 manifest_views:{label:'Stream views (manifest requests)',help:'Count of matching master manifest requests; an estimate of stream starts, not guaranteed unique plays.'},
 playtime_minutes:{label:'Estimated playtime (minutes)',help:'Calculated from matching six-second video segment requests, not a direct playback timer.'},
 bandwidth_bytes:{label:'Video bandwidth (bytes)',help:'Sum of matching video response bytes. Filter and metric definitions follow the source dashboard.'}
};
export const FIELD_LABELS={
 date:'Date (IST)',channel_name:'Channel',country:'Country',state:'State',city:'City',
 platform:'Device platform',operating_system:'Operating system',content_title:'Content title',hour_ist:'Hour (IST)',
 ...Object.fromEntries(Object.entries(DETAILS).map(([k,v])=>[k,v.label]))
};
export const PRESETS={
 overview:{title:'Daily overview',hint:'Users, sessions, views & playtime',selection:{kpis:['unique_devices','unique_ips','session_ids','manifest_views','playtime_minutes']}},
 channel:{title:'Top channels',hint:'Playtime and IP audience by channel',selection:{channel:['playtime_minutes','unique_ips']}},
 geo:{title:'Audience locations',hint:'Daily playtime by country, state and city',selection:{geo:['playtime_minutes']}},
 engagement:{title:'Watch-time & traffic',hint:'Playtime, streams and bandwidth',selection:{kpis:['playtime_minutes','manifest_views','bandwidth_bytes'],traffic:['manifest_views','playtime_minutes','bandwidth_bytes']}},
 content:{title:'Top shows',hint:'Title-level views, users & sessions',selection:{content:['manifest_views','unique_ips','unique_devices','session_ids']}},
 all:{title:'All available',hint:'All six certified report types',selection:Object.fromEntries(REPORT_ORDER.map(id=>[id,[...REPORTS[id].metrics]]))}
};
export const DEFAULT_SELECTION=PRESETS.overview.selection;
export function normalizeSelection(raw,{allowEmpty=false}={}){
 if(!raw||typeof raw!=='object'||Array.isArray(raw))throw new Error('Choose report parameters.');
 const result={};
 for(const id of REPORT_ORDER){
  const v=raw[id];if(v===undefined)continue;
  if(!Array.isArray(v))throw new Error(`Invalid metrics for ${id}.`);
  if(v.some(x=>!REPORTS[id].metrics.includes(x)))throw new Error(`Unsupported parameter in ${id}.`);
  const valid=REPORTS[id].metrics.filter(k=>v.includes(k));
  if(valid.length)result[id]=valid;
 }
 if(!allowEmpty&&!Object.keys(result).length)throw new Error('Select at least one metric to continue.');
 return result;
}
export function selectionReports(raw){return REPORT_ORDER.filter(id=>(normalizeSelection(raw,{allowEmpty:true})[id]||[]).length);}
export function selectionCounts(raw){const choice=normalizeSelection(raw,{allowEmpty:true});return{reports:Object.keys(choice).length,metrics:Object.values(choice).reduce((n,v)=>n+v.length,0)};}
export function selectedColumns(id,raw){
 if(!REPORTS[id]?.metrics)throw new Error('Unknown report category.');
 const selected=normalizeSelection(raw,{allowEmpty:true})[id]||[];
 if(!selected.length)throw new Error(`Choose at least one metric for ${id}.`);
 const wanted=[...REPORTS[id].dimension,...selected];
 return REPORT_COLUMNS[id].filter(([key])=>wanted.includes(key));
}
export function validateReports(ids){
 if(!Array.isArray(ids)||!ids.length||ids.length>REPORT_ORDER.length||ids.some(x=>!REPORT_ORDER.includes(x))||new Set(ids).size!==ids.length)throw new Error('Choose one or more supported report categories.');
 return REPORT_ORDER.filter(id=>ids.includes(id));
}
export function filterRecords(id,rows,filter){
 if(!Array.isArray(rows))throw new Error('Missing report rows.');
 if(!filter?.text)return rows;
 if(!REPORTS[id]?.dimension.includes(filter.field)||filter.field==='date')throw new Error('This category cannot use the selected filter.');
 const text=String(filter.text).trim().toLocaleLowerCase();
 if(text.length>120)throw new Error('Filter is too long.');
 return rows.filter(row=>String(row[filter.field]??'').toLocaleLowerCase().includes(text));
}

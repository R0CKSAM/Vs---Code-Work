import assert from 'node:assert/strict';
import {REPORT_ORDER, REPORTS, parseReportFrames} from '../reports.mjs';
import {parseGrafanaFrames} from '../core.mjs';
const from='2026-10-01',to='2026-10-03';let checks=0;
const cases={
 kpis:{report_date:['2026-10-01'],unique_devices:[120],unique_ips:[99],session_ids:[400],new_users:[72],returning_users:[48],ip_ua_sessions:[150],manifest_views:[500],session_hours:[1.68],avg_watch_minutes_per_user:[1.02],playtime_minutes:[100.5],bandwidth_bytes:[15000]},
 channel:{report_date:['2026-10-01'],channel_name:['India TV'],playtime_minutes:[100.5],unique_ips:[30]},
 geo:{report_date:['2026-10-01'],country:['IN'],state:['Delhi'],city:['NEWDELHI'],playtime_minutes:[100.5]},
 devices:{report_date:['2026-10-01'],platform:['Fire TV'],operating_system:['FireOS'],unique_devices:[19],unique_ips:[21]},
 content:{report_date:['2026-10-01'],content_title:['India TV'],manifest_views:[200],unique_ips:[25],unique_devices:[20],session_ids:[41]},
 traffic:{report_date:['2026-10-01'],hour_ist:['2026-10-01 12:00'],unique_ips:[100],session_ids:[300],manifest_views:[500],playtime_minutes:[250],bandwidth_bytes:[15000]}
};
const frame=columns=>({schema:{refId:'A',fields:Object.keys(columns).map(name=>({name}))},data:{values:Object.values(columns)}});
const payload=frames=>({results:{A:{status:200,frames}}});
for(const report of REPORT_ORDER){
 const f=frame(cases[report]), diag={};
 const rows=parseReportFrames(payload([f,f,f]),report,from,to,diag);
 assert.equal(rows.length,1);assert.equal(diag.duplicatesSkipped,2);checks+=2;
 const diff=structuredClone(cases[report]);
 const field=REPORTS[report].metrics[0];diff[field][0]+=1;
 assert.throws(()=>parseReportFrames(payload([f,frame(diff)]),report,from,to),/Conflicting .* data .* differed between Grafana frames/);
 checks++;
 // True distinct groups are preserved, even when dates match.
 const second=structuredClone(cases[report]);const d=REPORTS[report].dimension.find(x=>x!=='date');
 if(d){second[d][0]=d==='hour_ist'?'2026-10-01 13:00':'Second '+second[d][0];const clean=parseReportFrames(payload([f,frame(second)]),report,from,to);assert.equal(clean.length,2);checks++;}
}
const f=frame(cases.geo),d={};
const r=parseGrafanaFrames(payload([f,f]),from,to,d);
assert.equal(r.length,1);assert.equal(d.duplicatesSkipped,1);checks+=2;
const conflicting=structuredClone(cases.geo);conflicting.playtime_minutes[0]+=1;
assert.throws(()=>parseGrafanaFrames(payload([f,frame(conflicting)]),from,to),/Conflicting GEO playtime/);checks++;
console.log('PASS',checks,'duplicate-frame safety assertions: identical rows skipped, conflicting metrics refused, valid groups preserved.');

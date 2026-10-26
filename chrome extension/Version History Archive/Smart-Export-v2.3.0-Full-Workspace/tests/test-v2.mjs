import assert from 'node:assert/strict';
import fs from 'node:fs';
import {sqlForReport,REPORT_ORDER,parseReportFrames,rowsToCsv,assertSourcePanels} from '../reports.mjs';
import {rowIdentity} from '../report-db.mjs';
import {buildReportWorkbook} from '../multi-xlsx.mjs';
const from='2026-10-01',to='2026-10-03';let passes=0;
const check=(name,fn)=>{fn();console.log('PASS',name);passes++;};
const fields={
 kpis:{report_date:['2026-10-01','2026-10-02'],unique_devices:[120,130],unique_ips:[99,104],session_ids:[400,420],ip_ua_sessions:[150,160],manifest_views:[500,560],playtime_minutes:[100.5,108.75],bandwidth_bytes:[15000,17000]},
 channel:{report_date:['2026-10-01','2026-10-02'],channel_name:['Veto Cricket','News'],playtime_minutes:[100.5,108.25],unique_ips:[30,41]},
 geo:{report_date:['2026-10-01','2026-10-02'],country:['IN','IN'],state:['Delhi','UP'],city:['New Delhi','Noida'],playtime_minutes:[100.5,108.25]},
 devices:{report_date:['2026-10-01','2026-10-02'],platform:['Fire TV','Samsung TV'],operating_system:['FireOS','Tizen'],unique_devices:[19,22],unique_ips:[21,23]},
 content:{report_date:['2026-10-01','2026-10-02'],content_title:['Episode 1','=INJECT()'],manifest_views:[200,220],unique_ips:[25,28],unique_devices:[20,22],session_ids:[41,42]},
 traffic:{report_date:['2026-10-01','2026-10-02'],hour_ist:['2026-10-01 12:00','2026-10-02 14:00'],unique_ips:[100,200],session_ids:[300,400],manifest_views:[500,600],playtime_minutes:[250,270],bandwidth_bytes:[15000,17000]}
};
const mock={};
for(const id of REPORT_ORDER){const v=fields[id];mock[id]={results:{A:{frames:[{schema:{fields:Object.keys(v).map(name=>({name}))},data:{values:Object.values(v)}}]}}};}
const byReport={};
for(const id of REPORT_ORDER){
 check('SQL has bounded time '+id,()=>{const s=sqlForReport(id,from,to);assert.match(s,/reqTimeSec >= toDateTime\(/);assert.match(s,/reqTimeSec < toDateTime\(/);assert(!s.includes('$__adHocFilter()'));});
 if(id==='geo')byReport[id]=[{date:'2026-10-01',country:'IN',state:'Delhi',city:'New Delhi',playtime_minutes:100.5},{date:'2026-10-02',country:'IN',state:'UP',city:'Noida',playtime_minutes:108.25}];
 else byReport[id]=parseReportFrames(mock[id],id,from,to);
 check('Parsed '+id,()=>assert.equal(byReport[id].length,2));
 check('Distinct IDs '+id,()=>assert.notEqual(rowIdentity('source',id,byReport[id][0]),rowIdentity('source',id,byReport[id][1])));
}
check('CSV Excel injection protection',()=>{const out=rowsToCsv('content',byReport.content);assert.match(out,/"'=INJECT\(\)"/);});
check('reject missing field',()=>assert.throws(()=>parseReportFrames({results:{A:{frames:[{schema:{fields:[{name:'report_date'}]},data:{values:[['2026-10-01']]}}]}}},'kpis',from,to),/Missing expected/));
check('reject dup group',()=>{const dup=JSON.parse(JSON.stringify(mock.kpis));for(const v of dup.results.A.frames[0].data.values)v.push(v[0]);assert.throws(()=>parseReportFrames(dup,'kpis',from,to),/Duplicate/);});
check('reject out-of-range',()=>assert.throws(()=>parseReportFrames(mock.traffic,'traffic','2026-10-02',to),/out-of-range/));
check('reject duplicate source ids or missing panel',()=>assert.throws(()=>assertSourcePanels('geo',[]),/missing/));
const blob=buildReportWorkbook(byReport,{report:'executive',from,to});
check('workbook blob',()=>{assert.equal(blob.type,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');assert(blob.size>8000);});
fs.writeFileSync(new URL('./master-sample.xlsx',import.meta.url),Buffer.from(await blob.arrayBuffer()));
for(const id of REPORT_ORDER){const small=buildReportWorkbook(byReport,{report:id,from,to});check('single workbook '+id,()=>assert(small.size>4000));}
console.log(`${passes} V2 assertions passed`);

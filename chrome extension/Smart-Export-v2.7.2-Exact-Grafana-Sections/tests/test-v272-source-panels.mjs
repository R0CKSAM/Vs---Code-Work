import assert from 'node:assert/strict';
import fs from 'node:fs';
import {SECTIONS} from '../grafana-panel-catalog.mjs';
import {REPORTS, REPORT_COLUMNS, ALL_REPORT_ORDER, sqlForReport, parseReportFrames, assertSourcePanels} from '../reports.mjs';
import {normalizeSelection,selectedColumns,selectionReports} from '../metric-catalog.mjs';
import {rowIdentity} from '../report-db.mjs';
import {selectedCsv} from '../picked-export.mjs';
import {buildPickedWorkbook} from '../multi-xlsx.mjs';
const fixture=JSON.parse(fs.readFileSync(new URL('source-v272-panel-map.json',import.meta.url)));
const all=SECTIONS.flatMap(x=>x.panels);
assert.equal(SECTIONS.length,9);
assert.equal(all.length,34);
assert.deepEqual(SECTIONS.map(x=>x.title),fixture.map(x=>x.title));
for(let i=0;i<SECTIONS.length;i++){
 assert.deepEqual(SECTIONS[i].panels.map(p=>p.panel),fixture[i].panels.map(p=>p.id));
 for(let j=0;j<SECTIONS[i].panels.length;j++){
  const p=SECTIONS[i].panels[j],target=fixture[i].panels[j];
  assert.equal(p.name.replace(/\s+/g,' ').trim(),target.title.replace(/\s+/g,' ').trim(),`title mismatch ${p.panel}`);
  assert(REPORTS[p.report]?.sourceIds.includes(p.panel));
  assert((p.fields||[p.field]).every(f=>REPORTS[p.report].metrics.includes(f)));
 }
}
for(const section of SECTIONS.slice(1,6)){
 assert.equal(section.panels.length,2);
 assert.equal(section.style,'series');
 const [m,five]=section.panels;
 assert(m.report.endsWith('_1m')&&five.report.endsWith('_5m'));
 const sql1=sqlForReport(m.report,'2026-10-20','2026-10-20');
 const sql5=sqlForReport(five.report,'2026-10-20','2026-10-20');
 assert(sql1.includes('toStartOfMinute')&&sql1.includes('minute_ist'));
 assert(sql5.includes('row_number() OVER')&&sql5.includes('WHERE ranked=5')&&sql5.includes('cumulative_sum_5_min'));
 assert(sql1.includes('reqTimeSec >=')&&sql5.includes('reqTimeSec <'));
 assert(sql1.includes('%H:%i')&&sql5.includes('%H:%i'),'Minutes must use %i; %M returns month names on the live Hydrolix server');
 assert(!sql1.includes('$__adHocFilter()'));
}
assert(sqlForReport('ts_views_1m','2026-10-20','2026-10-20').includes("URL like '%main.m3u8%'"));
assert(sqlForReport('viewership_minute','2026-10-20','2026-10-20').includes('%H:%i'));
assert(!sqlForReport('ts_views_5m','2026-10-20','2026-10-20').includes("URL like '%main.m3u8%'"));
for(const key of ['viewership_stats','viewership_minute','geo_ips','platform_devices','os_devices','platform_ips','os_ips']){
 const sql=sqlForReport(key,'2026-10-20','2026-10-20');
 assert(sql.includes('toDateTime('));
}
const selected={ts_device_1m:['value'],ts_device_5m:['value'],os_ips:['unique_ips'],viewership_stats:['total_segments']};
const norm=normalizeSelection(selected);
assert.deepEqual(selectionReports(norm),Object.keys(norm));
assert.deepEqual(selectedColumns('ts_device_1m',norm).map(a=>a[0]),['date','minute_ist','value']);
const minuteRows={report_date:['2026-10-20','2026-10-20'],minute_ist:['2026-10-20 00:00','2026-10-20 00:01'],value:[23,36]};
const mock=(fields)=>({results:{A:{frames:[{schema:{fields:Object.keys(fields).map(name=>({name}))},data:{values:Object.values(fields)}}]}}});
const rows=parseReportFrames(mock(minuteRows),'ts_device_1m','2026-10-20','2026-10-20');
assert.equal(rows.length,2);assert.equal(rowIdentity('src','ts_device_1m',rows[0])!==rowIdentity('src','ts_device_1m',rows[1]),true);
assert.throws(()=>parseReportFrames(mock({...minuteRows,minute_ist:['2026-10-20 00:00','2026-10-21 00:01']}),'ts_device_1m','2026-10-20','2026-10-20'),/Invalid IST time bucket/);
const fiveRows=parseReportFrames(mock({report_date:['2026-10-20'],bucket_5m_ist:['2026-10-20 00:05'],value:[234]}),'ts_device_5m','2026-10-20','2026-10-20');
assert.equal(fiveRows[0].value,234);
assert.throws(()=>parseReportFrames(mock({report_date:['2026-10-20'],bucket_5m_ist:['2026-10-20 00:07'],value:[2]}),'ts_device_5m','2026-10-20','2026-10-20'),/misaligned/);
assert.match(selectedCsv('ts_device_1m',rows,norm),/Minute \(IST\)/);
const workbook=buildPickedWorkbook({ts_device_1m:rows,ts_device_5m:fiveRows,os_ips:[{date:'2026-10-20',operating_system:'iOS',unique_ips:123}],viewership_stats:[{date:'2026-10-20',total_segments:78}]},{selection:norm,from:'2026-10-20',to:'2026-10-20',perMetricSheets:true});
fs.writeFileSync('/mnt/data/Smart-Export-v2.7.2-Panel-Test.xlsx',Buffer.from(await workbook.arrayBuffer()));
assert(workbook.size>3500);
console.log('PASS 34 exact Grafana panels across 9 sections; 10 real series reports; source-aware 1/5 minute SQL; exports and time/date guards');

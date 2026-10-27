import {availableExport,selectedCsv} from '../picked-export.mjs';
import {buildPickedWorkbook} from '../multi-xlsx.mjs';
import {parseReportFrames} from '../reports.mjs';

// Browser-compatible checks; returned workbooks can also be inspected by Excel readers.
export async function testAvailableExport(){
 let checks=0;
 const check=(condition,message)=>{if(!condition)throw new Error(message);checks++;};
 const throws=(fn,pattern)=>{try{fn();}catch(e){check(pattern.test(e.message),e.message);return;}throw new Error('Expected failure');};
 const geo=[
  {date:'2026-10-20',country:'IN',state:'Delhi',city:'',playtime_minutes:123.5},
  {date:'2026-10-20',country:'IN',state:null,city:null,playtime_minutes:0},
  {date:'2026-10-20',country:'IN',playtime_minutes:null},
  {date:'2026-10-20',country:'IN',city:'Mumbai'},
  {date:'2026-10-20',country:'IN',state:'Maharashtra',city:'=1+1',playtime_minutes:42}
 ];
 const before=JSON.stringify(geo),choice={geo:['playtime_minutes'],channel:['unique_ips']};
 const prepared=availableExport({geo,channel:[]},choice);
 check(prepared.skipped.join(',')==='channel','Empty section must be reported');
 check(Object.keys(prepared.selection).join(',')==='geo','Only available sections should be selected');
 check(prepared.missingCells===8,'Missing fields must be counted separately from zero');
 check(JSON.stringify(geo)===before,'Export must preserve stored rows');
 const csv=selectedCsv('geo',geo,choice);
 check(csv.split('\r\n').length===7,'CSV must retain every row');
 check(csv.includes('"IN","","","0"'),'Blank dimensions and real zero must be retained');
 check(csv.includes('"IN","","",""'),'Absent values must remain blank');
 check(csv.includes('"\'=1+1"'),'CSV formula protection must remain active');
 throws(()=>availableExport({},choice),/No saved data/);
 throws(()=>selectedCsv('geo',[{date:'2026-10-20',playtime_minutes:NaN}],choice),/Invalid playtime_minutes/);
 throws(()=>selectedCsv('geo',[{date:'2026-10-20',playtime_minutes:Infinity}],choice),/Invalid playtime_minutes/);
 throws(()=>selectedCsv('geo',[{date:null}],choice),/Invalid date/);
 const parsed=parseReportFrames({results:{A:{frames:[{schema:{fields:['report_date','country','state','city','playtime_minutes'].map(name=>({name}))},data:{values:[['2026-10-20'],['IN'],[null],[null],[12]]}}]}}},'geo','2026-10-20','2026-10-20');
 check(parsed[0].city===''&&parsed[0].playtime_minutes===12,'Null Grafana city must survive parsing');
 check(selectedCsv('geo',parsed,choice).includes('"IN","","","12"'),'Grafana null GEO must export');
 const kpis=[{date:'2026-10-20',manifest_views:100},{date:'2026-10-21',manifest_views:null},{date:'2026-10-22',manifest_views:0}];
 const blobs={
  grouped:buildPickedWorkbook(prepared.rows,{...prepared,from:'2026-10-20',to:'2026-10-20'}),
  perMetric:buildPickedWorkbook(prepared.rows,{...prepared,from:'2026-10-20',to:'2026-10-20',perMetricSheets:true}),
  missingMetric:buildPickedWorkbook({kpis},{selection:{kpis:['manifest_views']},from:'2026-10-20',to:'2026-10-22'})
 };
 const workbooks={};
 for(const [name,blob] of Object.entries(blobs)){
  check(blob.size>3000,`${name} workbook must be generated`);
  workbooks[name]=btoa(String.fromCharCode(...new Uint8Array(await blob.arrayBuffer())));
 }
 return {checks,csv,workbooks};
}

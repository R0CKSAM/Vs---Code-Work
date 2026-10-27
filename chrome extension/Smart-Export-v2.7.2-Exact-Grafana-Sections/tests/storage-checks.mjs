import {putReportsAtomically,allReportRows,clearReportRows} from '../report-db.mjs?real-storage';
const row=(date,value=1)=>({date,country:'IN',state:'Delhi',city:'',playtime_minutes:value});
let checks=0;
const check=(ok,message)=>{if(!ok)throw new Error(message);checks++;};
const rejects=async fn=>{try{await fn();}catch{checks++;return;}throw new Error('Expected storage rejection');};
async function run(){
 await putReportsAtomically('audit-A','2026-10-18','2026-10-19',{geo:[row('2026-10-18'),row('2026-10-19')]});
 await putReportsAtomically('audit-B','2026-10-18','2026-10-18',{geo:[row('2026-10-18',77)]});
 await putReportsAtomically('audit-A','2026-10-19','2026-10-19',{geo:[row('2026-10-19',42)],channel:[{date:'2026-10-19',channel_name:'Fixture',unique_ips:9,playtime_minutes:10}]});
 let data=await allReportRows('audit-A');
 check(data.geo.length===2&&data.geo.find(r=>r.date==='2026-10-19').playtime_minutes===42,'Replacement must preserve dates outside the requested range');
 check((await allReportRows('audit-B')).geo[0].playtime_minutes===77,'Other dashboard data must be isolated');
 await putReportsAtomically('audit-A','2026-10-19','2026-10-19',{geo:[row('2026-10-19',43)]});
 check((await allReportRows('audit-A')).channel.length===1,'Unselected sections must be retained');
 await rejects(()=>putReportsAtomically('audit-A','bad','2026-10-19',{geo:[row('2026-10-19')]}));
 await rejects(()=>putReportsAtomically('audit-A','2026-10-19','2026-10-19',{geo:[{country:'IN'}]}));
 await rejects(()=>putReportsAtomically('audit-A','2026-10-19','2026-10-19',{geo:[row('2026-10-19'),row('2026-10-19')]}));
 await rejects(()=>putReportsAtomically('audit-A','2026-10-19','2026-10-19',{geo:[]}));
 // Trigger a real DataCloneError after the transaction has deleted existing rows.
 await rejects(()=>putReportsAtomically('audit-A','2026-10-19','2026-10-19',{geo:[row('2026-10-19',99)],channel:[{date:'2026-10-19',channel_name:'Bad',bad:()=>{}}]}));
 data=await allReportRows('audit-A');
 check(data.geo.find(r=>r.date==='2026-10-19').playtime_minutes===43&&data.channel[0].channel_name==='Fixture','A failed insertion must roll back deletions and all selected reports');
 await putReportsAtomically('audit-A','2026-10-19','2026-10-19',{geo:[{...row('2026-10-19',44),datasetKey:'audit-B',report:'channel',id:'spoof'}]});
 data=await allReportRows('audit-A');
 check(data.geo.find(r=>r.date==='2026-10-19').playtime_minutes===44&&data.channel.length===1,'Input fields must not override storage identity');
 check((await allReportRows('audit-B')).geo[0].playtime_minutes===77,'Metadata override must not change another dashboard');
 await clearReportRows('audit-A');data=await allReportRows('audit-A');
 check(Object.values(data).every(rows=>rows.length===0),'Clearing a dashboard must remove all its sections');
 check((await allReportRows('audit-B')).geo.length===1,'Clearing one dashboard must retain other dashboards');
 return checks;
}
run().then(checks=>{document.getElementById('ui-test-result').textContent=JSON.stringify({status:'PASS',checks,storage:'actual IndexedDB transactions'});}).catch(error=>{document.getElementById('ui-test-result').textContent=JSON.stringify({status:'FAIL',error:error.stack});});

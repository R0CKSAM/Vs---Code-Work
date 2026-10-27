/* Independent v2 multi-report master. V1 GEO database remains untouched for rollback. */
import {ALL_REPORT_ORDER,REPORTS} from './reports.mjs';
const DB_NAME='smart-export-reports-v2';
const STORE='rows';
function getDb(){return new Promise((resolve,reject)=>{
  const r=indexedDB.open(DB_NAME,1);
  r.onupgradeneeded=()=>{const db=r.result;if(!db.objectStoreNames.contains(STORE)){
    const s=db.createObjectStore(STORE,{keyPath:'id'});
    s.createIndex('datasetKey','datasetKey',{unique:false});
  }};
  r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);
});}
function txDone(tx){return new Promise((ok,fail)=>{tx.oncomplete=()=>ok();tx.onerror=()=>fail(tx.error||new Error('Storage error'));tx.onabort=()=>fail(tx.error||new Error('Storage transaction aborted'));});}
export function rowIdentity(datasetKey,type,row){
  const dims=REPORTS[type]?.dimension;
  if(!dims||!ALL_REPORT_ORDER.includes(type))throw new Error('Invalid report type.');
  return JSON.stringify([datasetKey,type,...dims.map(d=>row[d])]);
}
export async function putReportsAtomically(datasetKey,from,to,byReport){
  const ids=Object.keys(byReport);
  if(!ids.length)throw new Error('No reports to merge.');
  let count=0;
  for(const type of ids){
    if(!ALL_REPORT_ORDER.includes(type))throw new Error('Invalid report type.');
    for(const row of byReport[type]){if(row.date<from||row.date>to)throw new Error('Refusing to store out-of-range report data.');rowIdentity(datasetKey,type,row);count++;}
  }
  if(count>120000)throw new Error('Too many records for a single update. Use a shorter date range.');
  const db=await getDb();
  try{
    const tx=db.transaction(STORE,'readwrite');const s=tx.objectStore(STORE);
    const rq=s.index('datasetKey').openCursor(IDBKeyRange.only(datasetKey));
    const promise=txDone(tx);const update=new Set(ids);const timestamp=new Date().toISOString();
    rq.onerror=()=>{try{tx.abort();}catch{}};
    rq.onsuccess=()=>{const cursor=rq.result;
      if(cursor){const v=cursor.value;if(update.has(v.report)&&v.date>=from&&v.date<=to)cursor.delete();cursor.continue();return;}
      // Insert after deletions have completed, in the same IndexedDB transaction.
      for(const type of ids)for(const row of byReport[type]){
        const id=rowIdentity(datasetKey,type,row);
        s.put({id,datasetKey,report:type,...row,updatedAt:timestamp});
      }
    };
    await promise;return count;
  }finally{db.close();}
}
export async function getReportRows(datasetKey,type){
  if(!ALL_REPORT_ORDER.includes(type))throw new Error('Unknown report.');
  const db=await getDb();
  try{return await new Promise((resolve,reject)=>{
    const t=db.transaction(STORE,'readonly');const r=t.objectStore(STORE).index('datasetKey').getAll(IDBKeyRange.only(datasetKey));
    r.onsuccess=()=>resolve((r.result||[]).filter(x=>x.report===type));r.onerror=()=>reject(r.error);
  });}finally{db.close();}
}
export async function allReportRows(datasetKey){
  const db=await getDb();try{return await new Promise((resolve,reject)=>{
    const t=db.transaction(STORE,'readonly'),r=t.objectStore(STORE).index('datasetKey').getAll(IDBKeyRange.only(datasetKey));
    r.onsuccess=()=>{const o=Object.fromEntries(ALL_REPORT_ORDER.map(id=>[id,[]]));for(const x of r.result||[])if(o[x.report])o[x.report].push(x);resolve(o);};r.onerror=()=>reject(r.error);
  });}finally{db.close();}
}
export async function clearReportRows(datasetKey){
  const db=await getDb();try{
    const tx=db.transaction(STORE,'readwrite'),s=tx.objectStore(STORE);
    const rq=s.index('datasetKey').openCursor(IDBKeyRange.only(datasetKey));
    rq.onsuccess=()=>{const c=rq.result;if(c){c.delete();c.continue();}};
    await txDone(tx);
  }finally{db.close();}
}

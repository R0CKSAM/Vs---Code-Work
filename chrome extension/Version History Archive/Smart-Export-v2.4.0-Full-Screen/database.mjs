/* IndexedDB is the master store. A downloaded workbook is a snapshot, never silently overwritten. */
const DB_NAME='smart-export-geo-v1'; const STORE='geoRows';
export function openStore() {
  return new Promise((resolve,reject)=>{
    const request=indexedDB.open(DB_NAME,1);
    request.onupgradeneeded=()=>{const d=request.result;if(!d.objectStoreNames.contains(STORE)){
      const s=d.createObjectStore(STORE,{keyPath:'id'});
      s.createIndex('dataset','datasetKey',{unique:false});
    }};
    request.onsuccess=()=>resolve(request.result);
    request.onerror=()=>reject(request.error);
  });
}
function done(tx){return new Promise((resolve,reject)=>{tx.oncomplete=()=>resolve();tx.onerror=()=>reject(tx.error||new Error('IndexedDB transaction error'));tx.onabort=()=>reject(tx.error||new Error('IndexedDB transaction aborted'));});}
export async function replaceRange(datasetKey, from, to, rows) {
  const db=await openStore();
  try {
    const tx=db.transaction(STORE,'readwrite');
    const store=tx.objectStore(STORE);
    const idx=store.index('dataset');
    const cursorReq=idx.openCursor(IDBKeyRange.only(datasetKey));
    const txDone=done(tx);
    cursorReq.onsuccess=()=>{
      const c=cursorReq.result;
      if(c){
        if(c.value.date>=from && c.value.date<=to)c.delete();
        c.continue();
      } else {
        // Insert only after the deletion scan completes; otherwise a cursor can
        // inadvertently see/delete newly inserted rows in the same transaction.
        const ts=new Date().toISOString();
        for(const r of rows){
          const id=JSON.stringify([datasetKey,r.date,r.country,r.state,r.city]);
          store.put({...r,datasetKey,id,updatedAt:ts});
        }
      }
    };
    await txDone;
    return rows.length;
  }finally{db.close();}
}
export async function readDataset(datasetKey) {
  const db=await openStore();
  try{
    return await new Promise((resolve,reject)=>{
      const tx=db.transaction(STORE,'readonly');
      const request=tx.objectStore(STORE).index('dataset').getAll(IDBKeyRange.only(datasetKey));
      request.onsuccess=()=>resolve(request.result||[]);
      request.onerror=()=>reject(request.error);
    });
  }finally{db.close();}
}
export async function clearDataset(datasetKey) {
  const db=await openStore();
  try{
    const tx=db.transaction(STORE,'readwrite');
    const idx=tx.objectStore(STORE).index('dataset');
    const cursorReq=idx.openCursor(IDBKeyRange.only(datasetKey));
    cursorReq.onsuccess=()=>{const c=cursorReq.result;if(c){c.delete();c.continue();}};
    await done(tx);
  }finally{db.close();}
}

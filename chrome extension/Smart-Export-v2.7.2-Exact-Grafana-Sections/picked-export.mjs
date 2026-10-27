/* Export-only presentation. Does not mutate stored Grafana records. */
import {selectedColumns,normalizeSelection,filterRecords} from './metric-catalog.mjs';
import {validYMD} from './core.mjs';
export function rowsForExport(allRows,rawSelection,filter,range=null){
 const selected=normalizeSelection(rawSelection);
 const out={};
 const categories=Object.keys(selected);
 for(const id of categories){
  const onlyFilter=categories.length===1?filter:null;
  out[id]=filterRecords(id,allRows[id]||[],onlyFilter).filter(row=>!range||row.date>=range.from&&row.date<=range.to);
 }
 return out;
}
const csvSafe=x=>{
 let s=String(x??'');
 if(/^[\s]*[=+@\-\t\r]/.test(s))s="'"+s;
 return '"'+s.replace(/"/g,'""')+'"';
};
// Missing dimensions and metrics remain blank; a missing measurement is not zero.
export function exportCellValue(report,key,value){
 if(key==='date'){
  if(!validYMD(value))throw new Error(`Invalid date in stored ${report} data.`);
  return value;
 }
 if(value===null||value===undefined||typeof value==='string'&&value.trim()==='')return '';
 if(typeof value==='string'||typeof value==='number'&&Number.isFinite(value))return value;
 throw new Error(`Invalid ${key} in stored ${report} data.`);
}
export function availableExport(rows,rawSelection){
 const requested=normalizeSelection(rawSelection),selection={},data={},skipped=[];
 let missingCells=0;
 for(const [id,metrics] of Object.entries(requested)){
  if(!Array.isArray(rows[id])||!rows[id].length){skipped.push(id);continue;}
  selection[id]=metrics;data[id]=rows[id];
  const columns=selectedColumns(id,requested);
  for(const row of rows[id])for(const [key] of columns){
   if(exportCellValue(id,key,row[key])==='')missingCells++;
  }
 }
 if(!Object.keys(selection).length)throw new Error('No saved data for the selected sections and dates. Click Get data or choose dates with saved rows.');
 return {selection,rows:data,skipped,missingCells};
}
export function selectedCsv(report,rows,choice){
 const columns=selectedColumns(report,choice);
 return '\uFEFF'+[columns.map(([,name])=>name),...rows.map(row=>columns.map(([key])=>exportCellValue(report,key,row[key])))]
   .map(values=>values.map(csvSafe).join(',')).join('\r\n')+'\r\n';
}

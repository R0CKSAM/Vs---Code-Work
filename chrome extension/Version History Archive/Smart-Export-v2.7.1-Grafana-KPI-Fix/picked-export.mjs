/* Export-only presentation. Does not mutate stored Grafana records. */
import {selectedColumns,normalizeSelection,filterRecords} from './metric-catalog.mjs';
export function rowsForExport(allRows,rawSelection,filter){
 const selected=normalizeSelection(rawSelection);
 const out={};
 const categories=Object.keys(selected);
 for(const id of categories){
  const onlyFilter=categories.length===1?filter:null;
  out[id]=filterRecords(id,allRows[id]||[],onlyFilter);
 }
 return out;
}
const csvSafe=x=>{
 let s=String(x??'');
 if(/^[\s]*[=+@\-\t\r]/.test(s))s="'"+s;
 return '"'+s.replace(/"/g,'""')+'"';
};
export function selectedCsv(report,rows,choice){
 const columns=selectedColumns(report,choice);
 for(const row of rows)for(const [key] of columns){
  if(key==='date'||typeof row[key]==='string'&&row[key]!=='' )continue;
  if(typeof row[key]!=='number'||!Number.isFinite(row[key]))throw new Error(`Missing ${key} in stored ${report} data. Click Get data to refresh these metrics before exporting.`);
 }
 return '\uFEFF'+[columns.map(([,name])=>name),...rows.map(row=>columns.map(([key])=>row[key]))]
   .map(values=>values.map(csvSafe).join(',')).join('\r\n')+'\r\n';
}

/* A compact offline XLSX writer: no third-party runtime, no remote dependency.
 * Writes typed date/number cells and formulas, with frozen headers and a metric dictionary. */
import {REPORT_ORDER,REPORT_COLUMNS,EXCEL_SHEETS,DEFINITIONS} from './reports.mjs';
const TE=new TextEncoder();
const esc=x=>String(x??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&apos;').replace(/[\x00-\x08\x0b\x0c\x0e-\x1f]/g,'');
const colName=n=>{let x=n+1,out='';while(x){out=String.fromCharCode(65+(x-1)%26)+out;x=Math.floor((x-1)/26);}return out;};
function serialYMD(s){const t=Date.parse(String(s)+'T00:00:00Z');if(!Number.isFinite(t))throw new Error('Invalid workbook date.');return (t-Date.UTC(1899,11,30))/86400000;}
const textCell=(r,c,x,s=0)=>`<c r="${colName(c)}${r}"${s?` s="${s}"`:''} t="inlineStr"><is><t xml:space="preserve">${esc(x)}</t></is></c>`;
const numberCell=(r,c,x,s=0)=>Number.isFinite(Number(x))?`<c r="${colName(c)}${r}"${s?` s="${s}"`:''}><v>${Number(x)}</v></c>`:textCell(r,c,'');
const formulaCell=(r,c,formula,style=0)=>`<c r="${colName(c)}${r}"${style?` s="${style}"`:''}><f>${esc(formula)}</f></c>`;
function buildSheet(columns,records,options={}){
  const width=columns.length, count=records.length+1, last=colName(width-1);
  let xml=`<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><dimension ref="A1:${last}${Math.max(count,2)}"/><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><sheetFormatPr defaultRowHeight="18"/><cols>`;
  columns.forEach((column,i)=>{const w=Math.max(14,Math.min(42,Number(column.width)||24));xml+=`<col min="${i+1}" max="${i+1}" width="${w}" customWidth="1"/>`;});
  xml+='</cols><sheetData><row r="1" ht="31" customHeight="1">';
  columns.forEach((c,i)=>{xml+=textCell(1,i,c.title,1);});xml+='</row>';
  for(let i=0;i<records.length;i++){
    const r=i+2;xml+=`<row r="${r}">`;
    records[i].forEach((v,c)=>{
      if(v?.formula)xml+=formulaCell(r,c,v.formula,v.format==='percent'?4:2);
      else if(v?.date)xml+=numberCell(r,c,serialYMD(v.date),5);
      else if(typeof v==='number')xml+=numberCell(r,c,v,Number.isInteger(v)?3:2);
      else xml+=textCell(r,c,v);
    });xml+='</row>';
  }
  xml+=`</sheetData><autoFilter ref="A1:${last}${Math.max(count,2)}"/></worksheet>`;
  return xml;
}
function crc32(u8){let c=0xFFFFFFFF;for(const b of u8){c^=b;for(let k=0;k<8;k++)c=(c>>>1)^(0xEDB88320&-(c&1));}return(c^0xFFFFFFFF)>>>0;}
function zip(files){
 const chunks=[],list=[];let at=0;
 const w16=(v,o,n)=>v.setUint16(o,n,true),w32=(v,o,n)=>v.setUint32(o,n>>>0,true);
 for(const [name,source] of files){const fn=TE.encode(name),data=TE.encode(source),crc=crc32(data);
  const h=new Uint8Array(30+fn.length),v=new DataView(h.buffer);
  w32(v,0,0x04034b50);w16(v,4,20);w16(v,6,0x800);w16(v,8,0);w16(v,10,0);w16(v,12,0);w32(v,14,crc);w32(v,18,data.length);w32(v,22,data.length);w16(v,26,fn.length);w16(v,28,0);h.set(fn,30);
  const d=new Uint8Array(46+fn.length),dv=new DataView(d.buffer);
  w32(dv,0,0x02014b50);w16(dv,4,20);w16(dv,6,20);w16(dv,8,0x800);w16(dv,10,0);w16(dv,12,0);w16(dv,14,0);w32(dv,16,crc);w32(dv,20,data.length);w32(dv,24,data.length);w16(dv,28,fn.length);w16(dv,30,0);w16(dv,32,0);w16(dv,34,0);w16(dv,36,0);w32(dv,38,0);w32(dv,42,at);d.set(fn,46);
  chunks.push(h,data);list.push(d);at+=h.length+data.length;
 }
 const cdsize=list.reduce((n,a)=>n+a.length,0),e=new Uint8Array(22),v=new DataView(e.buffer);
 w32(v,0,0x06054b50);w16(v,4,0);w16(v,6,0);w16(v,8,list.length);w16(v,10,list.length);w32(v,12,cdsize);w32(v,16,at);w16(v,20,0);
 return new Blob([...chunks,...list,e],{type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'});
}
function standardSheet(id,rows){
 const columns=REPORT_COLUMNS[id].map(([key,title])=>({key,title,width:key==='content_title'?40:key==='channel_name'?27:key==='operating_system'?23:key==='hour_ist'?23: key==='date'?16:26}));
 if(id==='kpis')columns.push({key:'view_dod',title:'Manifest views DoD %',width:25},{key:'play_dod',title:'Playtime DoD %',width:22});
 const data=[...rows].sort((a,b)=>a.date.localeCompare(b.date)||JSON.stringify(a).localeCompare(JSON.stringify(b))).map((r,i,arr)=>{
  const base=REPORT_COLUMNS[id].map(([key])=>key==='date'?{date:r.date}:r[key]);
  if(id==='kpis'){
   const prior=arr[i-1];
   if(prior){const excelRow=i+2,prevRow=excelRow-1;
    base.push({formula:`IF(A${excelRow}=A${prevRow}+1,IFERROR((F${excelRow}-F${prevRow})/F${prevRow},""),"")`,format:'percent'});
    base.push({formula:`IF(A${excelRow}=A${prevRow}+1,IFERROR((G${excelRow}-G${prevRow})/G${prevRow},""),"")`,format:'percent'});
   } else base.push('','');
  }
  return base;
 });
 return {name:EXCEL_SHEETS[id],xml:buildSheet(columns,data)};
}
function definitionsSheet(meta){
 const info=[
  ['Workbook generated (UTC)',new Date().toISOString()],
  ['Grafana dataset','Veto_Streamin.logs'],
  ['Timezone','Asia/Kolkata'],
  ['Export type',meta.report==='executive'?'Executive Workbook':meta.report],
  ['Date range',`${meta.from||'Stored history'} to ${meta.to||'Stored history'}`],
  ['Date grouping','Daily for KPIs/channel/GEO/devices/content; hourly IST for traffic'],
  ['Export method','Grafana Hydrolix datasource query via signed-in browser tab'],
  ['Filter handling','Ad hoc Grafana filters are not supported in this release'],
  ...DEFINITIONS
 ];
 return {name:'Definitions',xml:buildSheet([{title:'Metric / item',width:31},{title:'Definition / caveat',width:83}],info)};
}
export function buildReportWorkbook(byReport,meta){
 const selected=meta.report==='executive'?REPORT_ORDER:[meta.report];
 if(!selected.every(id=>REPORT_ORDER.includes(id)))throw new Error('Invalid workbook report selection.');
 for(const id of selected)if(!Array.isArray(byReport[id])||!byReport[id].length)throw new Error(`Missing ${id} master data. Fetch it before exporting the workbook.`);
 if(selected.reduce((n,id)=>n+byReport[id].length,0)>120000)throw new Error('Master is too large for one workbook. Export a shorter date range.');
 const sheets=[...selected.map(id=>standardSheet(id,byReport[id])),definitionsSheet(meta)];
 const ct=`<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>${sheets.map((_,i)=>`<Override PartName="/xl/worksheets/sheet${i+1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>`).join('')}</Types>`;
 const rel=`<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>`;
 const wb=`<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>${sheets.map((s,i)=>`<sheet name="${esc(s.name)}" sheetId="${i+1}" r:id="rId${i+1}"/>`).join('')}</sheets><calcPr calcId="191029" fullCalcOnLoad="1"/></workbook>`;
 const wbrel=`<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">${sheets.map((s,i)=>`<Relationship Id="rId${i+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet${i+1}.xml"/>`).join('')}<Relationship Id="rId${sheets.length+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>`;
 const styles=`<?xml version="1.0" encoding="UTF-8"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><numFmts count="3"><numFmt numFmtId="164" formatCode="#,##0.00"/><numFmt numFmtId="165" formatCode="0.00%"/><numFmt numFmtId="166" formatCode="yyyy-mm-dd"/></numFmts><fonts count="2"><font><sz val="10"/><name val="Aptos"/></font><font><b/><sz val="10"/><color rgb="FFFFFFFF"/><name val="Aptos"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF173449"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="6"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="1" borderId="0" xfId="0" applyFont="1" applyFill="1"/><xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/><xf numFmtId="1" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/><xf numFmtId="166" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/></cellXfs></styleSheet>`;
 return zip([
  ['[Content_Types].xml',ct],['_rels/.rels',rel],['xl/workbook.xml',wb],['xl/_rels/workbook.xml.rels',wbrel],['xl/styles.xml',styles],
  ...sheets.map((s,i)=>[`xl/worksheets/sheet${i+1}.xml`,s.xml])
 ]);
}

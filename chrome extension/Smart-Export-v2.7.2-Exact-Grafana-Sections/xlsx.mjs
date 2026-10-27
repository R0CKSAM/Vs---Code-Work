/* Zero-dependency, standards-compliant XLSX writer (ZIP store method).
   Only trusted workbook structure and safely XML-escaped cell content. */
import { normalizeRows, dailyTotals } from './core.mjs';
const TE=new TextEncoder();
const escapeXml=s=>String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&apos;').replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g,'');
const colName=n=>{let x=n+1,r='';while(x){r=String.fromCharCode(65+(x-1)%26)+r;x=Math.floor((x-1)/26);}return r;};
const textCell=(r,c,v,s=0)=>`<c r="${colName(c)}${r}"${s?` s="${s}"`:''} t="inlineStr"><is><t xml:space="preserve">${escapeXml(v)}</t></is></c>`;
const numCell=(r,c,v,s=0)=>Number.isFinite(Number(v))?`<c r="${colName(c)}${r}"${s?` s="${s}"`:''}><v>${Number(v)}</v></c>`:textCell(r,c,'');
const fCell=(r,c,f,s=0)=>`<c r="${colName(c)}${r}"${s?` s="${s}"`:''}><f>${escapeXml(f)}</f></c>`;
function worksheet(rows,widths,createCell) {
  const header=rows[0]||[];
  let xml=`<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><dimension ref="A1:${colName(header.length-1)}${rows.length}"/><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><sheetFormatPr defaultRowHeight="17"/><cols>`;
  widths.forEach((w,i)=>{xml+=`<col min="${i+1}" max="${i+1}" width="${w}" customWidth="1"/>`;});
  xml+='</cols><sheetData>';
  for(let i=0;i<rows.length;i++){
    const r=i+1; xml+=`<row r="${r}"${i===0?' ht="28" customHeight="1"':''}>`;
    rows[i].forEach((value,c)=>{xml+=createCell(r,c,value,i);});
    xml+='</row>';
  }
  xml+=`</sheetData><autoFilter ref="A1:${colName(header.length-1)}${rows.length}"/></worksheet>`;
  return xml;
}
function crc32(u8){let c=0xFFFFFFFF;for(const b of u8){c^=b;for(let k=0;k<8;k++)c=(c>>>1)^(0xEDB88320&-(c&1));}return(c^0xFFFFFFFF)>>>0;}
function zip(files){
  const chunks=[], directory=[];let pos=0;
  const w16=(v,o,n)=>{v.setUint16(o,n,true);};const w32=(v,o,n)=>{v.setUint32(o,n>>>0,true);};
  for (const [name,content] of files){
    const fn=TE.encode(name), data=TE.encode(content), crc=crc32(data);
    const h=new Uint8Array(30+fn.length),v=new DataView(h.buffer);
    w32(v,0,0x04034b50);w16(v,4,20);w16(v,6,0x0800);w16(v,8,0);w16(v,10,0);w16(v,12,0);
    w32(v,14,crc);w32(v,18,data.length);w32(v,22,data.length);w16(v,26,fn.length);w16(v,28,0);
    h.set(fn,30);chunks.push(h,data);
    const d=new Uint8Array(46+fn.length),dv=new DataView(d.buffer);
    w32(dv,0,0x02014b50);w16(dv,4,20);w16(dv,6,20);w16(dv,8,0x0800);w16(dv,10,0);w16(dv,12,0);w16(dv,14,0);
    w32(dv,16,crc);w32(dv,20,data.length);w32(dv,24,data.length);w16(dv,28,fn.length);
    w16(dv,30,0);w16(dv,32,0);w16(dv,34,0);w16(dv,36,0);w32(dv,38,0);w32(dv,42,pos);
    d.set(fn,46);directory.push(d);pos+=h.length+data.length;
  }
  const cdsize=directory.reduce((n,a)=>n+a.length,0);const e=new Uint8Array(22),ev=new DataView(e.buffer);
  w32(ev,0,0x06054b50);w16(ev,4,0);w16(ev,6,0);w16(ev,8,directory.length);w16(ev,10,directory.length);
  w32(ev,12,cdsize);w32(ev,16,pos);w16(ev,20,0);
  return new Blob([...chunks,...directory,e],{type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'});
}
export function makeWorkbook(dataRows){
  const sorted=normalizeRows(dataRows);
  if(sorted.length>100000)throw new Error('For more than 100,000 GEO rows, export a CSV instead.');
  const headers=['Date (IST)','Country','State','City','Playtime (minutes)'];
  const records=sorted.map(r=>[r.date,r.country,r.state,r.city,r.playtime_minutes]);
  const geo=worksheet([headers,...records],[17,18,25,26,23],(r,c,v,i)=>i===0?textCell(r,c,v,1):c===4?numCell(r,c,v,2):textCell(r,c,v));
  const totals=dailyTotals(sorted);
  const detailEnd=Math.max(2,records.length+1);
  const sumRows=[['Date (IST)','Total playtime (min)','Change vs previous day','Change %','GEO groups']];
  totals.forEach((t,i)=>{
    const r=i+2;
    // Use spreadsheet formulas so totals and DoD update if the GEO Daily values are edited.
    sumRows.push([t.date,{formula:`SUMIF('GEO Daily'!$A$2:$A$${detailEnd},A${r},'GEO Daily'!$E$2:$E$${detailEnd})`},i>0?{formula:`B${r}-B${r-1}`}:'',i>0?{formula:`IFERROR(C${r}/B${r-1},0)`}:'',{formula:`COUNTIF('GEO Daily'!$A$2:$A$${detailEnd},A${r})`}]);
  });
  const summary=worksheet(sumRows,[18,26,27,18,16],(r,c,v,i)=>{
    if(i===0)return textCell(r,c,v,1);
    if(v?.formula)return fCell(r,c,v.formula,c===3?3: c===4?4:2);
    return textCell(r,c,v);
  });
  const ct=`<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/></Types>`;
  const rootRel=`<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/></Relationships>`;
  const wb=`<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="GEO Daily" sheetId="1" r:id="rId1"/><sheet name="Daily Summary" sheetId="2" r:id="rId2"/></sheets><calcPr calcId="191029" fullCalcOnLoad="1"/></workbook>`;
  const wbRel=`<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>`;
  const styles=`<?xml version="1.0" encoding="UTF-8"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><numFmts count="2"><numFmt numFmtId="164" formatCode="#,##0.00"/><numFmt numFmtId="165" formatCode="0.00%"/></numFmts><fonts count="2"><font><sz val="11"/><name val="Aptos"/></font><font><b/><sz val="11"/><color rgb="FF000000"/><name val="Aptos"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FFE2E8F0"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="5"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFill="1" applyFont="1"/><xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/><xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/><xf numFmtId="1" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs></styleSheet>`;
  const core=`<?xml version="1.0" encoding="UTF-8"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:creator>Smart Export</dc:creator><dc:title>Playtime by GEO — Daily Master</dc:title></cp:coreProperties>`;
  return zip([
    ['[Content_Types].xml',ct],['_rels/.rels',rootRel],['xl/workbook.xml',wb],['xl/_rels/workbook.xml.rels',wbRel],['xl/styles.xml',styles],['xl/worksheets/sheet1.xml',geo],['xl/worksheets/sheet2.xml',summary],['docProps/core.xml',core]
  ]);
}

// Local-only CSV/XLSX reader. No CDN, uploads, or network requests.
const StoryboardImport=(()=>{
 const clean=s=>String(s??'').trim();
 function csv(text){
   const rows=[];let row=[],field='',quoted=false;
   text=String(text).replace(/^\uFEFF/,'');
   for(let i=0;i<text.length;i++){
     const c=text[i];
     if(quoted){if(c==='"'&&text[i+1]==='"'){field+='"';i++}else if(c==='"')quoted=false;else field+=c}
     else if(c==='"')quoted=true;
     else if(c===','){row.push(field);field=''}
     else if(c==='\n'||c==='\r'){if(c==='\r'&&text[i+1]==='\n')i++;row.push(field);if(row.some(v=>v.trim()))rows.push(row);row=[];field=''}
     else field+=c;
   }
   if(quoted)throw Error('A CSV quote is not closed. Export the spreadsheet as XLSX or a valid CSV.');
   row.push(field);if(row.some(v=>v.trim()))rows.push(row);
   return rows;
 }
 function xlsxIndex(a){
   const view=new DataView(a),u8=new Uint8Array(a);let end=-1;
   for(let p=u8.length-22;p>=Math.max(0,u8.length-65557);p--){if(view.getUint32(p,true)===0x06054b50){end=p;break}}
   if(end<0)throw Error('Invalid XLSX file: ZIP directory not found.');
   const count=view.getUint16(end+10,true),offset=view.getUint32(end+16,true);
   let pos=offset;const entries=new Map();
   for(let j=0;j<count;j++){
     if(view.getUint32(pos,true)!==0x02014b50)throw Error('Invalid XLSX directory.');
     const method=view.getUint16(pos+10,true),size=view.getUint32(pos+20,true),nameLen=view.getUint16(pos+28,true),extra=view.getUint16(pos+30,true),comment=view.getUint16(pos+32,true),local=view.getUint32(pos+42,true);
     const name=new TextDecoder().decode(u8.subarray(pos+46,pos+46+nameLen));
     const localName=view.getUint16(local+26,true),localExtra=view.getUint16(local+28,true);
     entries.set(name,{method,size,start:local+30+localName+localExtra});pos+=46+nameLen+extra+comment;
   }
   return {entries,u8};
 }
 async function extract(z,name){
   const item=z.entries.get(name);if(!item)throw Error(`XLSX missing ${name}`);
   const bytes=z.u8.slice(item.start,item.start+item.size);
   if(item.method===0)return new TextDecoder().decode(bytes);
   if(item.method!==8)throw Error('Unsupported XLSX compression.');
   const stream=new Blob([bytes]).stream().pipeThrough(new DecompressionStream('deflate-raw'));
   return new TextDecoder().decode(await new Response(stream).arrayBuffer());
 }
 const xml=t=>{const d=new DOMParser().parseFromString(t,'application/xml');if(d.querySelector('parsererror'))throw Error('Invalid XLSX XML.');return d};
 const nodes=(root,tag)=>Array.from(root.getElementsByTagNameNS('*',tag));
 async function xlsx(file){
   const z=xlsxIndex(await file.arrayBuffer());
   const shared=z.entries.has('xl/sharedStrings.xml')?nodes(xml(await extract(z,'xl/sharedStrings.xml')),'si').map(si=>nodes(si,'t').map(t=>t.textContent).join('')):[];
   const book=xml(await extract(z,'xl/workbook.xml'));
   const first=nodes(book,'sheet')[0];if(!first)throw Error('No worksheets found.');
   const rid=first.getAttribute('r:id');
   const rels=xml(await extract(z,'xl/_rels/workbook.xml.rels'));
   const rel=nodes(rels,'Relationship').find(r=>r.getAttribute('Id')===rid);
   let target=rel?.getAttribute('Target')||'worksheets/sheet1.xml';
   let path=target.startsWith('/')?target.slice(1):'xl/'+target;
   const parts=[];for(const p of path.split('/')){if(p==='..')parts.pop();else if(p!=='.')parts.push(p)}path=parts.join('/');
   const ws=xml(await extract(z,path));
   const result=nodes(ws,'row').map(row=>{
     const cells=[];cells.excelRow=Number(row.getAttribute('r'))||0;cells.formulas=[];
     for(const c of nodes(row,'c')){
       const ref=c.getAttribute('r')||'',letters=/^[A-Z]+/.exec(ref)?.[0]||'A';let col=0;
       for(const ch of letters)col=col*26+ch.charCodeAt(0)-64;
       if(nodes(c,'f').length)cells.formulas.push(col-1);
       const type=c.getAttribute('t');let value='';
       if(type==='inlineStr')value=nodes(c,'t').map(t=>t.textContent).join('');
       else {const v=nodes(c,'v')[0]?.textContent||'';value=type==='s'?shared[Number(v)]??'':v;}
       cells[col-1]=value;
     }
     return cells;
   });
   result.sheetNames=nodes(book,'sheet').map(s=>s.getAttribute('name'));
   return result;
 }
 function normalize(rows){
   // The spreadsheet ROW ORDER is the execution order. Frame identifiers are display labels ONLY.
   const at=rows.findIndex(r=>r.some(v=>clean(v).toLowerCase().replace(/[^a-z0-9]/g,'')==='sceneprompt'));
   if(at<0)throw Error('The first worksheet must have a Scene Prompt column. Other worksheets are not imported.');
   const header=rows[at].map(v=>clean(v).toLowerCase().replace(/[^a-z0-9]/g,''));
   const frame=header.indexOf('frame'),master=header.indexOf('masterprompt'),scene=header.indexOf('sceneprompt');
   for(const name of ['frame','masterprompt','sceneprompt'])if(header.filter(x=>x===name).length>1)throw Error('Duplicate column header: '+name+'. Keep only one of each storyboard column.');
   const prompts=[],warnings=[],invalid=[];let masterValue='';
   if(rows.sheetNames)warnings.push('Imported first worksheet: '+rows.sheetNames[0]+'.'+(rows.sheetNames.length>1?' Other '+(rows.sheetNames.length-1)+' worksheet(s) are not imported.':''));
   if(frame<0)warnings.push('No Frame column: spreadsheet row labels will be used.');
   if(master<0)warnings.push('No Master Prompt column: no global style prompt will be used.');
   const unused=header.filter(x=>x&&!['frame','masterprompt','sceneprompt'].includes(x));
   if(unused.length)warnings.push('Only Frame, Master Prompt and Scene Prompt are imported; '+unused.length+' additional column(s) are not used.');
   for(let i=at+1;i<rows.length;i++){
     const r=rows[i];if(!r.some(v=>clean(v))&&!(r.formulas||[]).length)continue;
     const number=r.excelRow||i+1,description=clean(r[scene]);
     if((r.formulas||[]).some(c=>[frame,master,scene].includes(c)))throw Error('Row '+number+' uses a formula in a storyboard column. Replace formulas with their text values before uploading.');
     if(!description){invalid.push(number);continue;}
     const label=frame<0?'':clean(r[frame]);const m=master<0?'':clean(r[master]);
     if(m&&masterValue&&m!==masterValue)throw Error('Row '+number+' has a different Master Prompt. Use one shared Master Prompt; put frame-specific instructions in Scene Prompt.');
     if(m&&!masterValue)masterValue=m;
     prompts.push(`${label||`Row ${i+1}`} || ${description}`);
   }
   if(invalid.length)throw Error('Missing Scene Prompt in row(s) '+invalid.slice(0,8).join(', ')+(invalid.length>8?' and more':'')+'. Fill these scenes or delete the incomplete rows. No frames were imported.');
   if(!prompts.length)throw Error('No scene prompts found. Add at least one nonempty Scene Prompt below the header.');
   return {master:masterValue,prompts,count:prompts.length,warnings};
 }
 async function read(file){const ext=file.name.toLowerCase().split('.').pop();
   if(ext==='txt'){const lines=(await file.text()).split(/\r?\n/).map(x=>x.trim()).filter(Boolean);if(!lines.length)throw Error('TXT file is empty.');return {master:null,prompts:lines,count:lines.length}}
   if(ext==='csv')return normalize(csv(await file.text()));
   if(ext==='xlsx'){try{const rows=await xlsx(file);return normalize(rows);}catch(e){throw Error('Please check your Excel file is in a compatible format. '+e.message);}}
   throw Error('Upload a .txt, .csv or .xlsx file.');
 }
 return {read,csv,normalize};
})();

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
   return nodes(ws,'row').map(row=>{
     const cells=[];
     for(const c of nodes(row,'c')){
       const ref=c.getAttribute('r')||'',letters=/^[A-Z]+/.exec(ref)?.[0]||'A';let col=0;
       for(const ch of letters)col=col*26+ch.charCodeAt(0)-64;
       const type=c.getAttribute('t');let value='';
       if(type==='inlineStr')value=nodes(c,'t').map(t=>t.textContent).join('');
       else {const v=nodes(c,'v')[0]?.textContent||'';value=type==='s'?shared[Number(v)]??'':v;}
       cells[col-1]=value;
     }
     return cells;
   });
 }
 function normalize(rows){
   // The spreadsheet ROW ORDER is the execution order. Frame identifiers are display labels ONLY.
   const at=rows.findIndex(r=>r.some(v=>clean(v).toLowerCase().replace(/[^a-z0-9]/g,'')==='sceneprompt'));
   if(at<0)throw Error('Missing Scene Prompt header.');
   const header=rows[at].map(v=>clean(v).toLowerCase().replace(/[^a-z0-9]/g,''));
   const frame=header.indexOf('frame'),master=header.indexOf('masterprompt'),scene=header.indexOf('sceneprompt');
   const prompts=[];let masterValue='';
   for(let i=at+1;i<rows.length;i++){
     const r=rows[i],description=clean(r[scene]);if(!description)continue;
     const label=frame<0?'':clean(r[frame]);const m=master<0?'':clean(r[master]);
     if(m&&!masterValue)masterValue=m;
     prompts.push(`${label||`Row ${i+1}`} || ${description}`);
   }
   if(!prompts.length)throw Error('No scene prompts found.');
   return {master:masterValue,prompts,count:prompts.length};
 }
 async function read(file){const ext=file.name.toLowerCase().split('.').pop();
   if(ext==='txt'){const lines=(await file.text()).split(/\r?\n/).map(x=>x.trim()).filter(Boolean);if(!lines.length)throw Error('TXT file is empty.');return {master:null,prompts:lines,count:lines.length}}
   if(ext==='csv')return normalize(csv(await file.text()));
   if(ext==='xlsx')return normalize(await xlsx(file));
   throw Error('Upload a .txt, .csv or .xlsx file.');
 }
 return {read,csv,normalize};
})();

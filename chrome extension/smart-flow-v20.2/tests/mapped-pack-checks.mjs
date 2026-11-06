import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const root=path.resolve(import.meta.dirname,'..');
const pack=process.argv[2];
if(!pack)throw Error('Pass the Aarohan_Reference_Pack folder.');
const context=vm.createContext({});
vm.runInContext(fs.readFileSync(path.join(root,'importer.js'),'utf8')+';globalThis.reader=StoryboardImport;',context);
const reader=context.reader;
let checks=0;
const manifest=reader.csv(fs.readFileSync(path.join(pack,'Attachment_Manifest.csv'),'utf8'));
const header=manifest.shift(),ids=new Map(manifest.map(r=>[r[0],r]));
assert.equal(ids.size,1444);checks++;
for(const name of fs.readdirSync(pack).filter(n=>/Prompts\.csv$|First_5_Test\.csv$/.test(n))){
 const raw=fs.readFileSync(path.join(pack,name),'utf8'),rows=reader.csv(raw),result=await reader.read(new File([raw],name));
 assert.equal(result.count,rows.length-1);assert.equal(result.mapped,true);assert.equal(result.master,'');checks+=3;
 for(let i=0;i<result.count;i++){
  const id=rows[i+1][0];assert.equal(result.prompts[i],id+' || '+rows[i+1][1].trim());assert(ids.has(id));checks+=2;
 }
}
for(const row of manifest){
 const refs=row[header.indexOf('Attach these actual files')].split(';').map(s=>s.trim()).filter(Boolean);
 assert(refs.length<=8);checks++;
 for(const name of refs){assert(fs.existsSync(path.join(pack,'references',name)));checks++;}
}
for(const text of ['Frame ID,Prompt\nX,one\nX,two','Frame ID,Prompt\nX,','Frame ID,Prompt\n,one']){
 assert.throws(()=>reader.normalize(reader.csv(text)));checks++;
}
assert.equal(reader.normalize(reader.csv('Frame,Master Prompt,Scene Prompt\n001,Anime,Inside the hall')).count,1);checks++;
console.log(JSON.stringify({status:'PASS',checks,frames:ids.size,originalTextAndOrderPreserved:true}));

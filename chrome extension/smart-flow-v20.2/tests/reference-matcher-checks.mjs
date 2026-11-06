import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
await import(pathToFileURL(path.resolve(import.meta.dirname,'../reference-matcher.js')));
const matcher=globalThis.SmartFlowReferenceMatcher;
const pack=process.argv[2],names=fs.readdirSync(path.join(pack,'references')).filter(n=>/\.(png|jpe?g|webp)$/i.test(n));
const data=matcher.catalog(names.filter(n=>n!=='Aarohan technical crew reference board.png'));let checks=0;
for(const name of ['Kavita','Rhea','Dev','Aarav','Nandini','Mahendra',"Trisha's mother",'festival coordinator']){
 assert.deepEqual(matcher.resolve(name,data).files,['CAST_SUPPORT.png']);checks++;
}
for(const name of ['Anaya','Arjun','Mehak','Trisha','Veer']){assert.deepEqual(matcher.resolve(name,data).files,['CHAR_'+name.toUpperCase()+'.png']);checks++;}
assert.deepEqual(matcher.resolve("Anaya's mother",data).files,['CAST_SUPPORT.png']);checks++;
assert.deepEqual(matcher.resolve('device development',data).files,[]);checks++;
assert.deepEqual(matcher.request('Please attach Rhea reference image. I already have the festival location reference.',data).files,['CAST_SUPPORT.png']);checks++;
assert.deepEqual(matcher.request('I used the Rhea reference image to generate this scene.',data),null);checks++;
assert.deepEqual(matcher.request('Please attach Stagehand and Young Volunteer reference images.',data).missing,['Stagehand','Young Volunteer']);checks++;
assert.deepEqual(matcher.request('Please attach CHAR_UNLISTED.png reference.',data).missing,['CHAR_UNLISTED.png']);checks++;
assert.deepEqual(matcher.castFiles('CURRENT VISIBLE CAST / CROP: KAVITA, ANAYA\nBackground: Arjun home',data).sort(),['CAST_SUPPORT.png','CHAR_ANAYA.png']);checks++;
const expanded=matcher.catalog([...names,'CHAR_STAGEHAND.png']);assert.deepEqual(matcher.resolve('Stagehand',expanded),{files:['CHAR_STAGEHAND.png'],missing:[]});checks++;
assert.throws(()=>matcher.catalog(names,{version:1,entries:[{file:'no-such-file.png',aliases:['Rhea']}]}));checks++;
assert.equal(data.entries.length,14);checks++;
const full=matcher.catalog(names,JSON.parse(fs.readFileSync(path.join(pack,'Reference_Catalog.json'),'utf8')));
for(const text of ['Stagehand','Young Volunteer','Volunteer','Please attach Aarohan technical crew reference board.png']){const result=matcher.resolve(text,full);assert.deepEqual(result.files,['Aarohan technical crew reference board.png']);assert.deepEqual(result.missing,[]);checks+=2;}
console.log(JSON.stringify({status:'PASS',checks,indexedFiles:full.entries.length,verifiedNamedCharacters:15,unmapped:[]}));

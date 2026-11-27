import test from 'node:test';
import assert from 'node:assert/strict';
import {correctionPrompt,MAX_CORRECTIONS,promptFor,sizeFolder,isSource,stem} from '../core.mjs';
test('download follow-up requests exact file without padding',()=>{
 const p=correctionPrompt({key:'video-key',w:400,h:711},'correction-id','1024 × 1536');
 for(const s of ['job correction-id','400 × 711','video-key.png','1024 × 1536','actual file','blank padding','Do not advance','AI-generated thumbnail','must not rebuild'])assert.ok(p.includes(s));
});
test('automatic follow-ups are bounded',()=>assert.equal(MAX_CORRECTIONS,2));
test('prompt carries unique checkpoint and preservation requirements',()=>{
 const p=promptFor({token:'abc',name:'key.jpg',w:400,h:711},'Use orange');
 for(const s of ['job abc','400 × 711','wording and spelling','IMAGE GENERATION','Use orange','downloadable','not assemble','background','SAME people','Fill the canvas edge to edge'])assert.ok(p.includes(s));
});
test('video keys and folders preserved',()=>{assert.equal(sizeFolder({w:1920,h:1080}),'1920 × 1080 px');assert.equal(stem('my.video.jpg'),'my.video');assert.ok(isSource('IMAGE.WEBP'));assert.ok(!isSource('download_report.csv'));});

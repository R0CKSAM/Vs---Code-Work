import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import fs from 'node:fs';
const source=fs.readFileSync(new URL('../background.js',import.meta.url),'utf8');
test('file bridge captures matching Blob before revocation and restores hooks',async()=>{
 let next=0,normal=0;const blobUrls=new Map();
 class Anchor{constructor(name,url){this.download=name;this.href=url;}click(){normal++;}dispatchEvent(){normal++;}}
 const originalClick=Anchor.prototype.click;
 const pageURL={createObjectURL:b=>{const url='blob:test/'+ ++next;blobUrls.set(url,b);return url;}};
 const originalURL=pageURL.createObjectURL;
 class Reader{readAsDataURL(blob){blob.arrayBuffer().then(b=>{this.result='data:'+blob.type+';base64,'+Buffer.from(b).toString('base64');this.onload();});}}
 const chrome={action:{onClicked:{addListener(){}}},runtime:{onInstalled:{addListener(){}},onMessage:{addListener(){}}}};
 const context=vm.createContext({chrome,window:{},URL:pageURL,HTMLAnchorElement:Anchor,document:{addEventListener(){},removeEventListener(){}},FileReader:Reader,setTimeout,clearTimeout,Map});
 vm.runInContext(source,context);
 const pending=context.capturePageDownload('key.png');
 new Anchor('unrelated.png',pageURL.createObjectURL(new Blob(['other']))).click();
 const url=pageURL.createObjectURL(new Blob(['exact image bytes'],{type:'image/png'}));new Anchor('key.png',url).click();blobUrls.delete(url);
 const r=await pending;assert.equal(r.ok,true);assert.equal(r.dataUrl,'data:image/png;base64,'+Buffer.from('exact image bytes').toString('base64'));assert.equal(normal,1);assert.equal(Anchor.prototype.click,originalClick);assert.equal(pageURL.createObjectURL,originalURL);assert.equal(context.window.__smartBannerFileCapture,undefined);
});

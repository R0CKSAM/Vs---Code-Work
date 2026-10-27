import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {pathToFileURL,fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
const out=fs.mkdtempSync(path.join(os.tmpdir(),'smart-export-audit-'));
let failures=0;
for(const file of fs.readdirSync(root).filter(n=>n.endsWith('.mjs'))){
 const r=spawnSync(process.execPath,['--check',path.join(root,file)],{encoding:'utf8',timeout:15000});
 if(r.status!==0){console.log('FAIL syntax',file,r.stderr);failures++;}
}
for(const file of ['test-core.mjs','test-v2.mjs','test-picker.mjs','test-picker-background.mjs','test-v23-tab-nav.mjs','test-v24-duplicate-recovery.mjs','test-v271-panel-parity.mjs','test-v272-source-panels.mjs','test-production-background.mjs']){
 if(!fs.existsSync(path.join(root,'tests',file)))continue;
 const code=`import fs from 'node:fs';import path from 'node:path';import {fileURLToPath} from 'node:url';const original=fs.writeFileSync;fs.writeFileSync=(p,data,...args)=>original(path.join(${JSON.stringify(out)},path.basename(p instanceof URL?fileURLToPath(p):String(p))),data,...args);await import(${JSON.stringify(pathToFileURL(path.join(root,'tests',file)).href)});`;
 const r=spawnSync(process.execPath,['--experimental-vm-modules','--input-type=module','-e',code],{cwd:root,encoding:'utf8',timeout:30000});
 if(r.status!==0){console.log('FAIL',file,(r.stderr||r.error?.message||r.stdout).slice(-2000));failures++;}
 else console.log('PASS',file,r.stdout.trim().split('\n').at(-1));
}
console.log('Generated test artifacts:',out);
console.log('Failures:',failures);
process.exitCode=failures?1:0;


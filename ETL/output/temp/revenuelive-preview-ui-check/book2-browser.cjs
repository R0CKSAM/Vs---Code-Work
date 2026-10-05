const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const path=require('node:path');
const [url,workbook]=process.argv.slice(2);
(async()=>{
  assert(new URL(url).hostname==='127.0.0.1');
  const browser=await chromium.launch({channel:'msedge',headless:true});
  try{
    for(const width of [1440,390]){
      const page=await browser.newPage({viewport:{width,height:1000}}),errors=[],consolidationRequests=[];
      page.on('request',request=>{if(request.url().endsWith('/consolidate'))consolidationRequests.push(request.url());});
      page.on('pageerror',error=>errors.push(error.message));
      page.on('dialog',dialog=>dialog.accept());
      await page.goto(url);
      await page.locator('#loginForm [name=username]').fill('admin');
      await page.locator('#loginForm [name=password]').fill('synthetic-password');
      await page.locator('#loginForm button.primary').click();
      await page.locator('#shell').waitFor({state:'visible'});
      await page.evaluate(()=>document.getElementById('uploadNav').click());
      await page.locator('#uploadForm input[type=file]').setInputFiles(workbook);
      await page.locator('#uploadForm button.primary').click();
      await page.locator('#preview').waitFor({state:'visible',timeout:30000});
      assert.equal(await page.evaluate(()=>pending.rows.length),4044);
      assert.equal(consolidationRequests.length,0,'Backend must prepare the preview without a second request');
      assert.equal(await page.evaluate(()=>pending.rows.some(row=>row.blocking_error||row.entry_group)),false);
      assert.match(await page.locator('#previewWarning').innerText(),/2 total mismatches/);
      const id=await page.evaluate(()=>pending.id);
      assert.equal(await page.locator('#combineEntries,#skipExactEntries,#resolveEntries').count(),0);
      assert.match(await page.locator('#entrySummary').innerText(),/1 exact duplicate copy skipped/);
      assert.equal(await page.evaluate(()=>pending.rows.length),4044);
      await page.locator('#acceptTotals').check();
      await page.locator('#previewOnlyWarnings').uncheck();
      await page.locator('#previewSearch').fill('2026-09-18 3587');
      await page.locator('#previewSearch').fill('MP Govt');
      await page.locator('#preview').scrollIntoViewIfNeeded();
      await page.screenshot({path:path.join(__dirname,`book2-${width}.png`),fullPage:true});
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
      await page.locator('#previewSearch').fill('');
      await page.locator('#publish').click();
      await page.locator('#preview').waitFor({state:'hidden'});
      const history=await page.evaluate(()=>api('/api/uploads?show_archived=1'));
      const item=history.rows.find(row=>row.id===id);
      assert.equal(item.state,'committed');
      await page.evaluate(async id=>{await api('/api/uploads/'+id+'/delete',{method:'POST'});},id);
      assert.deepEqual(errors,[]);
      console.log(`Book2 actual browser ${width}px: upload, preview, consolidation, acceptance and publish PASS`);
      await page.close();
    }
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});

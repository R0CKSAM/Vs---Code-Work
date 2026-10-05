const {chromium}=require('playwright');
const fs=require('node:fs/promises');
const path=require('node:path');
const assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../../../RevenueLive');
const rows=Array.from({length:1400},(_,i)=>({source_row:i+2,day:'2026-09-01',channel:'Synthetic Channel',views:100,impressions:40,ad:500,other:169900,total:170400}));
for(const n of [318,1378])rows[n-2].warning={source_row:n,code:'total_mismatch',supplied_total:'1705',rounded_supplied_total:170500,calculated_total:170400};
const preview={id:'synthetic-upload',state:'pending',duplicates:0,unchanged:0,rows};
(async()=>{
  const browser=await chromium.launch({channel:'msedge',headless:true});
  try{
    for(const viewport of [{width:1440,height:1000},{width:390,height:844}]){
      const page=await browser.newPage({viewport});
      const errors=[],commits=[];
      page.on('pageerror',e=>errors.push(e.message));
      page.on('dialog',dialog=>dialog.accept());
      await page.route('http://preview.test/**',async route=>{
        const request=route.request(),url=new URL(request.url());
        if(url.pathname.startsWith('/api/')){
          if(url.pathname.endsWith('/commit'))commits.push(request.postDataJSON());
          return route.fulfill({status:url.pathname==='/api/me'?401:200,contentType:'application/json',body:JSON.stringify(url.pathname==='/api/me'?{error:'Please sign in.'}:{ok:true,rows:[],uploads_version:2})});
        }
        const relative=url.pathname.startsWith('/static/')?url.pathname.slice(1):'static/index.html';
        const file=path.resolve(root,relative);
        assert(file.startsWith(root+path.sep));
        const types={'.html':'text/html','.css':'text/css','.js':'application/javascript','.png':'image/png','.svg':'image/svg+xml','.json':'application/json'};
        await route.fulfill({contentType:types[path.extname(file)]||'application/octet-stream',body:await fs.readFile(file)});
      });
      await page.goto('http://preview.test/login');
      await page.waitForFunction(()=>typeof openUploadPreview==='function');
      await page.waitForTimeout(500);
      await page.evaluate(preview=>{
        document.getElementById('login').hidden=true;
        document.getElementById('shell').hidden=false;
        document.querySelectorAll('.view').forEach(view=>view.hidden=view.id!=='uploads');
        openUploadPreview(preview);
      },preview);
      assert.equal(await page.locator('#previewRows tr').count(),2);
      assert.match(await page.locator('#previewRows').innerText(),/318/);
      assert.match(await page.locator('#previewRows').innerText(),/1,378/);
      await page.locator('#preview').scrollIntoViewIfNeeded();
      await page.screenshot({path:path.join(__dirname,`preview-${viewport.width}.png`),fullPage:true});
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Unexpected page overflow');
      await page.locator('#publish').click();
      assert.equal(commits.length,0,'Missing acknowledgement must not publish');
      await page.locator('#previewOnlyWarnings').uncheck();
      assert.equal(await page.locator('#previewRows tr').count(),100);
      await page.locator('#previewNext').click();
      assert.match(await page.locator('#previewPageStatus').innerText(),/101-200/);
      await page.locator('#acceptTotals').check();
      await page.locator('#publish').click();
      await page.waitForFunction(()=>document.getElementById('preview').hidden);
      assert.equal(commits.length,1);
      assert.equal(commits[0].accept_total_mismatches,true);
      await page.evaluate(preview=>{
        const value=structuredClone(preview);
        value.rows[0].blocking_error='Duplicate date/channel; first appears at Excel row 2.';
        openUploadPreview(value);
      },preview);
      assert.equal(await page.locator('#previewRows .preview-blocked').count(),1);
      assert(await page.locator('#publish').isDisabled());
      const channelChoices=[{id:1,name:'Example'}];
      let resolutionRequests=[];
      await page.route('http://preview.test/api/uploads/preview',route=>{
        const raw=route.request().postDataBuffer().toString('utf8');
        const field=raw.match(/name="channel_actions"\r\n\r\n([^\r]+)/);
        const actions=field?JSON.parse(field[1]):[];
        if(actions.length){
          resolutionRequests=actions;
          channelChoices.push({id:2,name:'Fixed New Channel'});
          const decisions=actions.map(action=>({...action,channel_id:action.action==='create'?2:1,channel:action.action==='create'?'Fixed New Channel':'Example'}));
          return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({...preview,rows:[{...rows[0]}],channel_resolutions:decisions,channels:channelChoices})});
        }
        return route.fulfill({status:400,contentType:'application/json',body:JSON.stringify({error:'3 channels need attention.',code:'upload_channel_issues',channel_options:channelChoices,channel_issues:[
        {channel:'New Channel <test>',status:'unknown',rows:Array.from({length:12},(_,i)=>i+2)},
        {channel:'Assigned Elsewhere',status:'unassigned',rows:[318,1378]},
        {channel:'Old Channel',status:'archived',rows:[17]}
      ]})});});
      await page.evaluate(()=>{pending=null;document.getElementById('preview').hidden=true;});
      await page.locator('#uploadForm input[type=file]').setInputFiles({name:'synthetic.csv',mimeType:'text/csv',buffer:Buffer.from('synthetic fixture')});
      await page.locator('#uploadForm button[type=submit], #uploadForm button:not([type])').click();
      await page.locator('#uploadChannelIssues').waitFor({state:'visible'});
      assert.equal(await page.locator('#uploadChannelIssueRows tr').count(),3);
      assert.match(await page.locator('#uploadChannelIssueRows').innerText(),/Not assigned to you/);
      assert.match(await page.locator('#uploadChannelIssueRows').innerText(),/Not registered/);
      assert.equal(await page.locator('#uploadChannelIssueRows test').count(),0);
      await page.locator('#uploadChannelIssueRows summary').click();
      assert.match(await page.locator('#uploadChannelIssueRows details span').innerText(),/12, 13/);
      await page.locator('#applyChannelResolutions').click();
      assert.match(await page.locator('#channelResolutionError').innerText(),/Resolve every/);
      await page.locator('[data-channel-resolution="0"]').selectOption('create');
      await page.locator('[data-new-channel-name="0"]').fill('Fixed New Channel');
      await page.locator('[data-channel-resolution="1"]').selectOption('map:1');
      await page.locator('[data-channel-resolution="2"]').selectOption('map:1');
      await page.screenshot({path:path.join(__dirname,`channels-${viewport.width}.png`),fullPage:true});
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Channel issue panel overflow');
      const account={user:{id:2,username:'synthetic-uploader',role:'uploader',must_change:0},channels:channelChoices,csrf:'test-only'};
      await page.route('http://preview.test/api/me',route=>route.fulfill({contentType:'application/json',body:JSON.stringify({...account,channels:channelChoices})}));
      await page.evaluate(account=>{me=account;csrf=account.csrf;selectedChannels=new Set(['1']);},account);
      await page.locator('#applyChannelResolutions').click();
      await page.locator('#previewChannelChanges').waitFor({state:'visible'});
      assert.equal(resolutionRequests.length,3);
      assert.equal(resolutionRequests[0].name,'Fixed New Channel');
      assert.equal(resolutionRequests[1].channel_id,1);
      assert.match(await page.locator('#previewChannelChanges').innerText(),/Added:.*Fixed New Channel/);
      assert.match(await page.locator('#previewChannelChanges').innerText(),/Matched:/);
      await page.evaluate(()=>syncAccess());
      assert(await page.locator('#preview').isVisible(),'Self-assignment must not discard the preview');
      assert.equal(await page.evaluate(()=>me.channels.length),2);
      assert.deepEqual(errors,[]);
      console.log(`Preview ${viewport.width}px: warning acceptance, channel create/map, confirmation and access sync PASS`);
      await page.close();
    }
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});

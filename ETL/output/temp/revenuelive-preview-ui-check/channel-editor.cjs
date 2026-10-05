const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const path=require('node:path');
const fs=require('node:fs/promises');
const root=path.resolve(__dirname,'../../../RevenueLive');
(async()=>{
  const browser=await chromium.launch({channel:'msedge',headless:true});
  const logo=await fs.readFile(path.join(root,'static/channel-logos/9xm.png'));
  try{
    for(const width of [1440,390]){
      const page=await browser.newPage({viewport:{width,height:900}});
      const errors=[];page.on('pageerror',error=>errors.push(error.message));
      await page.goto(process.env.CHANNEL_TEST_URL);
      await page.locator('#loginForm input[name=username]').fill('admin');
      await page.locator('#loginForm input[name=password]').fill('synthetic-password');
      await page.locator('#loginForm button.primary').click();
      await page.locator('#dashboard').waitFor({state:'visible'});
      await page.locator('#accountMenu > summary').click();
      await page.locator('#adminNav').click();
      await page.locator('[data-edit-channel="1"]').click();
      const form=page.locator('#channelEditForm');
      await form.locator('[name=name]').fill('Example '+width);
      await form.locator('[name=logo]').setInputFiles({name:'channel.png',mimeType:'image/png',buffer:logo});
      await page.locator('#channelLogoPreview img').waitFor({state:'visible'});
      await page.screenshot({path:path.join(__dirname,`channel-editor-${width}.png`)});
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
      assert(await page.locator('#channelEditDialog').evaluate(el=>el.scrollWidth<=el.clientWidth+1));
      let response=page.waitForResponse(r=>r.url().endsWith('/api/admin/channels/1')&&r.request().method()==='POST');
      await form.locator('[type=submit]').click();
      assert.equal((await response).status(),200);
      await page.locator('#channelEditDialog').waitFor({state:'hidden'});
      assert.match(await page.locator('#channelDirectory').innerText(),new RegExp('Example '+width));
      const image=page.locator('[data-directory-logo="1"] img');
      await image.waitFor({state:'visible'});
      assert.match(await image.getAttribute('src'),/\/api\/channels\/1\/logo/);
      assert(await image.evaluate(async img=>{await img.decode();return img.naturalWidth>0}));
      await page.locator('[data-edit-channel="1"]').click();
      await form.locator('[name=reset_logo]').check();
      response=page.waitForResponse(r=>r.url().endsWith('/api/admin/channels/1')&&r.request().method()==='POST');
      await form.locator('[type=submit]').click();
      assert.equal((await response).status(),200);
      await page.locator('#channelEditDialog').waitFor({state:'hidden'});
      assert.equal(await page.locator('[data-directory-logo="1"] img').count(),0);
      assert.deepEqual(errors,[]);
      console.log(`Channel editor ${width}px: rename, logo upload, rendering, reset and layout PASS`);
      await page.close();
    }
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1});

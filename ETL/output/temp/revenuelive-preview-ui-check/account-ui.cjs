const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const path=require('node:path');
(async()=>{
  const browser=await chromium.launch({channel:'msedge',headless:true});
  try{
    const page=await browser.newPage();
    const errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.goto(process.env.ACCOUNT_TEST_URL);
    await page.locator('#loginForm input[name=username]').fill('admin');
    await page.locator('#loginForm input[name=password]').fill('synthetic-password');
    await page.locator('#loginForm button.primary').click();
    await page.locator('#dashboard').waitFor({state:'visible'});
    await page.evaluate(()=>document.getElementById('adminNav').click());
    await page.locator('#users tr').first().waitFor();
    assert.match(await page.locator('#users').innerText(),/Recovery email missing/);
    for(const width of [1440,390]){
      await page.setViewportSize({width,height:1000});
      await page.locator('#addUser').click();
      assert(await page.locator('#inviteEmail').isDisabled());
      await page.locator('#userForm input[name=username]').fill('viewer-'+width);
      await page.locator('#userForm input[name=email]').fill('viewer-'+width+'@example.com');
      await page.locator('#userForm input[name=password]').fill('temporary-password');
      assert(await page.locator('#userDialog').evaluate(el=>el.scrollWidth<=el.clientWidth+1));
      await page.locator('#userDialog').screenshot({path:path.join(__dirname,`account-create-${width}.png`)});
      await page.locator('#userForm button.primary').click();
      await page.locator('#userDialog').waitFor({state:'hidden'});
      const row=page.locator('#users tr').filter({hasText:'viewer-'+width+'@example.com'});
      await row.getByRole('button',{name:'Edit',exact:true}).click();
      assert.equal(await page.locator('#userForm input[name=email]').inputValue(),'viewer-'+width+'@example.com');
      assert(await page.locator('#inviteEmail').isHidden());
      await page.locator('#userForm input[name=email]').fill('updated-'+width+'@example.com');
      await page.locator('#userForm button.primary').click();
      await page.locator('#userDialog').waitFor({state:'hidden'});
      await page.locator('#users tr').filter({hasText:'updated-'+width+'@example.com'}).waitFor();
      console.log(`Accounts ${width}px: create, edit, recovery email, invitation state and dialog overflow PASS`);
    }
    await page.evaluate(()=>document.getElementById('passwordButton').click());
    await page.locator('#passwordDialog').waitFor({state:'visible'});
    assert(await page.locator('#passwordForm input[name=email]').isVisible());
    await page.locator('#passwordCancel').click();
    assert.deepEqual(errors,[]);
    console.log('Own recovery email field and browser error checks PASS');
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});

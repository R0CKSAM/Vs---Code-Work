const {chromium}=require('playwright');
const fs=require('node:fs/promises');
const path=require('node:path');
const assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../../../RevenueLive');
const categories=[['all','All activity',106],['access','Login / Logout',103],['passwords','Passwords',1],['uploads','Uploads',1],['live','Live / Unlive',1],['archive','Archive / Restore',0],['delete','Deleted',0],['users','Users',0],['channels','Channels',0],['other','Other',0]].map(([id,label,count])=>({id,label,count}));
(async()=>{
  const browser=await chromium.launch({channel:'msedge',headless:true});
  try{
    for(const width of [1440,390]){
      const page=await browser.newPage({viewport:{width,height:1000}}),errors=[];
      page.on('pageerror',error=>errors.push(error.message));
      await page.route('http://preview.test/**',async route=>{
        const url=new URL(route.request().url());
        if(url.pathname==='/api/admin/audit'){
          const category=url.searchParams.get('category')||'all',current=Number(url.searchParams.get('page')||1);
          const total=categories.find(item=>item.id===category).count;
          const events=Array.from({length:Math.max(0,Math.min(50,total-(current-1)*50))},(_,i)=>({
            id:total-(current-1)*50-i,created:'2026-10-05T08:00:00Z',actor:'Admin <test>',
            action:category==='passwords'?'password_changed':'user_signed_in',detail:'Synthetic event',category}));
          if(category==='passwords')await new Promise(resolve=>setTimeout(resolve,180));
          return route.fulfill({json:{valid:true,count:106,head:'synthetic',categories,category,page:current,pages:Math.max(1,Math.ceil(total/50)),page_size:50,total,events}});
        }
        if(url.pathname.startsWith('/api/'))return route.fulfill({status:url.pathname==='/api/me'?401:200,json:{error:'Synthetic anonymous session',rows:[]}});
        const relative=url.pathname.startsWith('/static/')?url.pathname.slice(1):'static/index.html';
        const file=path.resolve(root,relative);
        assert(file.startsWith(root+path.sep));
        const types={'.html':'text/html','.css':'text/css','.js':'application/javascript','.png':'image/png','.svg':'image/svg+xml'};
        await route.fulfill({contentType:types[path.extname(file)]||'application/octet-stream',body:await fs.readFile(file)});
      });
      await page.goto('http://preview.test/login');
      await page.waitForTimeout(400);
      await page.evaluate(async()=>{
        document.getElementById('login').hidden=true;document.getElementById('shell').hidden=false;
        document.querySelectorAll('.view').forEach(view=>view.hidden=view.id!=='uploads');
        document.getElementById('uploadAdminControls').hidden=false;
        document.getElementById('uploadAuditPanel').open=true;
        await loadAuditHistory();
      });
      await page.locator('#auditCategories button').first().waitFor();
      assert.equal(await page.locator('#auditCategories button').count(),10);
      await page.locator('[data-audit-category=access]').click();
      await page.waitForFunction(()=>document.getElementById('auditPageStatus').textContent==='1-50 of 103 events');
      await page.locator('#auditNext').click();
      await page.waitForFunction(()=>document.getElementById('auditPageStatus').textContent==='51-100 of 103 events');
      await page.locator('#auditNext').click();
      await page.waitForFunction(()=>document.getElementById('auditPageStatus').textContent==='101-103 of 103 events');
      assert(await page.locator('#auditNext').isDisabled());
      assert.equal(await page.locator('#auditEvents tr').count(),3);
      assert.equal(await page.locator('#auditEvents test').count(),0);
      await page.locator('[data-audit-category=passwords]').click();
      await page.locator('[data-audit-category=delete]').click();
      await page.waitForTimeout(300);
      assert.match(await page.locator('#auditEvents').innerText(),/No activity in this category/);
      await page.locator('[data-audit-category=passwords]').click();
      await page.waitForFunction(()=>document.getElementById('auditEvents').textContent.includes('password changed'));
      await page.locator('#uploadAuditPanel').scrollIntoViewIfNeeded();
      await page.screenshot({path:path.join(__dirname,`audit-${width}.png`),fullPage:true});
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Page overflow');
      const overlaps=await page.locator('#auditCategories button').evaluateAll(buttons=>buttons.some((button,i)=>buttons.slice(i+1).some(other=>{
        const a=button.getBoundingClientRect(),b=other.getBoundingClientRect();
        return Math.min(a.right,b.right)>Math.max(a.left,b.left)+1&&Math.min(a.bottom,b.bottom)>Math.max(a.top,b.top)+1;
      })));
      assert.equal(overlaps,false);
      assert.deepEqual(errors,[]);
      console.log(`Activity ${width}px: categories, counts, paging, empty state, escaping and request race PASS`);
      await page.close();
    }
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});

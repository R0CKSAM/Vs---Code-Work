const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const path=require('node:path');
(async()=>{
  const isolated=process.env.TIMELINE_TEST_URL;
  const browser=isolated?await chromium.launch({channel:'msedge',headless:true}):await chromium.connectOverCDP('http://127.0.0.1:9448');
  const page=isolated?await browser.newPage():browser.contexts()[0].pages().find(p=>p.url().startsWith('http://127.0.0.1:8820'));
  if(isolated){await page.goto(isolated);await page.locator('#loginForm input[name=username]').fill('admin');await page.locator('#loginForm input[name=password]').fill('synthetic-password');await page.locator('#loginForm button.primary').click();await page.locator('#dashboard').waitFor({state:'visible'});}
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.reload();await page.locator('#timelineScope').waitFor({state:'visible'});
  await page.evaluate(()=>{
    document.getElementById('datePreset').value='custom';document.getElementById('start').value='2026-02-20';document.getElementById('end').value='2026-09-29';document.getElementById('filters').requestSubmit();
  });
  await page.waitForTimeout(1400);
  const state=()=>page.evaluate(()=>{const chart=Chart.getChart('dailyRevenueCanvas');return {type:chart.config.type,points:chart.data.labels.length,sum:chart.data.datasets.flatMap(d=>d.data).reduce((a,n)=>a+(n??0),0),kpi:document.getElementById('total').textContent,share:document.getElementById('shareSum').textContent};});
  const baseline=await state();assert.equal(baseline.points,8);assert.equal(baseline.type,'bar');
  const expected=await page.evaluate(async()=>{
    const query=new URLSearchParams({start:'2026-02-20',end:'2026-09-29'});
    for(const input of document.querySelectorAll('#channelOptions input:checked'))query.append('channel',input.value);
    const data=await(await fetch('/api/report?'+query)).json();return data.totals.total/100;
  });
  assert(Math.abs(baseline.sum-expected)<0.001);
  for(const width of [1440,390]){
    await page.setViewportSize({width,height:1000});
    await page.locator('[data-timeline-interval="auto"]').click();
    await page.locator('#revenueOverview').scrollIntoViewIfNeeded();
    await page.waitForTimeout(250);
    await page.locator('#revenueOverview').screenshot({path:path.join(__dirname,`timeline-monthly-${width}.png`)});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
    await page.locator('#timelinePeriod').selectOption('4');
    assert.match(await page.locator('#timelineScope').innerText(),/Daily breakdown/);
    assert.equal((await state()).points,30);
    assert.equal((await state()).kpi,baseline.kpi);assert.equal((await state()).share,baseline.share);
    await page.locator('#timelineBack').click();assert.equal((await state()).points,8);
    await page.locator('[data-timeline-interval="week"]').click();
    assert((await state()).points>25&&(await state()).points<35);assert(Math.abs((await state()).sum-expected)<0.001);
    await page.locator('[data-timeline-interval="day"]').click();assert.equal((await state()).points,222);
    assert(Math.abs((await state()).sum-expected)<0.001);
    await page.locator('[data-timeline-interval="auto"]').click();
    await page.locator('.timeline-expand').click();await page.locator('#timelineDetailDialog').waitFor({state:'visible'});
    await page.locator('#timelinePeriod').selectOption('6');assert.equal((await state()).points,31);
    await page.locator('#timelineBack').click();
    await page.locator('#timelineDetailDialog').screenshot({path:path.join(__dirname,`timeline-expanded-${width}.png`)});
    assert(await page.locator('#timelineDetailDialog').evaluate(el=>el.scrollWidth<=el.clientWidth+1));
    await page.getByRole('button',{name:'Close expanded timeline',exact:true}).click();
    for(const metric of ['Views','Ad impressions','Revenue']){
      await page.getByRole('button',{name:metric,exact:true}).click();
      assert.equal((await state()).points,8);assert.equal((await state()).type,metric==='Revenue'?'bar':'line');
    }
    console.log(`Timeline ${width}px: 8 monthly buckets, conserved totals, isolated drill-down, weekly/daily, metric switch and expanded controls PASS`);
  }
  await page.setViewportSize({width:1440,height:1000});
  await page.locator('[data-timeline-interval="auto"]').click();
  await page.locator('#dailyRevenueCanvas').scrollIntoViewIfNeeded();
  await page.waitForTimeout(400);
  const hit=await page.evaluate(()=>{const chart=Chart.getChart('dailyRevenueCanvas'),bar=chart.getDatasetMeta(0).data[4],rect=chart.canvas.getBoundingClientRect();return {x:rect.x+bar.x,y:rect.y+(bar.y+bar.base)/2};});
  await page.mouse.click(hit.x,hit.y);await page.waitForTimeout(200);assert.match(await page.locator('#timelineScope').innerText(),/Daily breakdown/);
  await page.locator('#timelineBack').click();
  assert(await page.locator('#dailyRevenueCanvas').evaluate(canvas=>{const data=canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data;return data.some((n,i)=>i%4===3&&n>0);}));
  await page.evaluate(()=>window.scrollTo(0,0));await page.bringToFront();
  assert.deepEqual(errors,[]);console.log('Bar click drill-down, rendered canvas and browser error checks PASS');
  if(isolated)await browser.close();process.exit(0);
})().catch(error=>{console.error(error);process.exit(1)});

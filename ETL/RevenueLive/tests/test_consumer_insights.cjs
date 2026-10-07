const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const context = {window: {}, URLSearchParams, Intl};
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../static/quick-insights.js'), 'utf8'), context);
const {build, curate} = context.window.QuickInsights;
const row = (day, id, value=100) => ({day, channel_id:id, channel:'Channel '+id, views:value, impressions:value*2, ad:value*100, other:0, total:value*100});
const query = 'start=2026-10-01&end=2026-10-02&channel=1&channel=2';
const current = {rows:[row('2026-10-01',1),row('2026-10-01',2),row('2026-10-02',1)]};
const previous = {rows:[row('2026-09-29',1,50),row('2026-09-29',2,50),row('2026-09-30',1,50),row('2026-09-30',2,50)]};
function check(items) {
  for (const item of items) {
    assert.notEqual(item.kind, 'warning');
    assert.equal(item.parts.map(part=>part.text).join(''),item.evidence);
    assert(!/incomplete|missing uploads|unavailable|decline|decreased|negative|NaN|Infinity/i.test(item.title+' '+item.evidence));
  }
}
let items=build(current,query,previous,'ready');
check(items);
assert(items.some(i=>i.id==='recorded-views' && i.evidence.includes('300')));
assert(!items.some(i=>i.id.startsWith('change-')||i.id==='peak-views'));
assert(curate(items).length>4);
assert(items.find(i=>i.id==='recorded-views').parts.some(p=>p.emphasis&&p.text==='300'));
assert(items.find(i=>i.id==='leader-views').parts.some(p=>p.emphasis&&p.text==='Channel 1'));
const hostile={rows:[{...row('2026-10-01',1),channel:'<img src=x onerror=alert(1)>'},row('2026-10-01',2,50)]};
const safe=build(hostile,'start=2026-10-01&end=2026-10-01&channel=1&channel=2',null,'ready');
assert(safe.find(i=>i.id==='leader-views').parts.some(p=>p.emphasis&&p.text==='<img src=x onerror=alert(1)>'));
current.rows.push(row('2026-10-02',2));
items=build(current,query,previous,'ready');
check(items);
assert(items.some(i=>i.id==='change-views' && i.evidence.includes('+100.0%')));
const higher={rows:previous.rows.map(r=>({...r,views:1000,impressions:2000,ad:100000,total:100000}))};
items=build(current,query,higher,'ready');
check(items);
assert(!items.some(i=>i.id.startsWith('change-')||i.id==='decliner'));
check(build(current,query,null,'unavailable'));
assert.equal(build({rows:[]},query).length,0);
assert.equal(build({rows:[row('2026-10-01',1,0)]},'start=2026-10-01&end=2026-10-01&channel=1').length,0);
console.log('PASS: factual consumer highlights, incomplete coverage, growth/decline, zero and empty data');

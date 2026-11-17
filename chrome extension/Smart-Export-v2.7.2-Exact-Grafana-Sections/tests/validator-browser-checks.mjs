const wait=async fn=>{const start=Date.now();while(!fn()){if(Date.now()-start>6000)throw Error('UI timeout');await new Promise(r=>setTimeout(r,25));}};
const $=id=>document.getElementById(id);let checks=0;function check(ok,msg){if(!ok)throw Error(msg);checks++;}
const done=document.createElement('pre');done.id='ui-test-result';done.textContent='PENDING';document.body.append(done);
try{
 await wait(()=>$('referenceInfo').textContent.includes('fixture.parquet')&&!$('saved').disabled);
 check($('scope').options.length===1,'Reference scopes rendered');check($('availability').children.length>=10,'Field availability visible');
 $('saved').click();await wait(()=>$('snapshotInfo').textContent.includes('saved snapshot')&&!$('compare').disabled);
 check($('from').value==='2026-10-20','Saved data chooses a represented shared date');
 $('compare').click();await wait(()=>$('results').textContent.includes('Scope / rules unverified'));
 check(!$('exportCsv').disabled,'Comparison export enabled');check($('results').textContent.includes('Definition mismatch'),'Known mismatch visible');
 for(const id of ['scopeConfirmed','rulesConfirmed']){$(id).checked=true;$(id).dispatchEvent(new Event('change'));}
 check($('exportAudit').disabled,'Changed inputs invalidate downloadable audit');$('compare').click();await wait(()=>$('results').textContent.includes('Within tolerance'));
 check($('results').textContent.includes('Definition mismatch'),'Manual review cannot override known formula mismatch');
 let downloads=[];const old=HTMLAnchorElement.prototype.click;HTMLAnchorElement.prototype.click=function(){downloads.push(this.download);};$('exportCsv').click();$('exportAudit').click();HTMLAnchorElement.prototype.click=old;
 check(downloads.length===2&&downloads[0].endsWith('.csv')&&downloads[1].endsWith('.json'),'Both downloads work');
 $('tolerance').value='-1';$('tolerance').dispatchEvent(new Event('change'));$('compare').click();await wait(()=>$('notice').textContent.includes('Tolerance must'));
 check($('notice').className==='error','Invalid tolerance has a visible error');$('tolerance').value='1';
 $('dashboard').value+='&var-filter=country%7C%3D%7CIN';$('dashboard').dispatchEvent(new Event('change'));$('compare').click();await wait(()=>$('notice').textContent.includes('Read saved'));
 check($('exportCsv').disabled,'Changing dashboard clears stale comparison/snapshot');
 $('connect').click();await wait(()=>$('notice').textContent.includes('Connected')&&!$('live').disabled);
 $('live').click();await wait(()=>$('notice').textContent.includes('Live snapshot ready')&&!$('compare').disabled);
 check($('snapshotInfo').textContent.includes('live snapshot'),'Live snapshot and provenance rendered');check(!$('scopeConfirmed').checked,'Live fetch resets unverified scope');
 $('compare').click();await wait(()=>$('results').textContent.includes('Scope / rules unverified'));
 check(document.documentElement.scrollWidth<=innerWidth+2,'Responsive page fits viewport');
 done.textContent=JSON.stringify({status:'PASS',checks,width:innerWidth});
}catch(e){done.textContent=JSON.stringify({status:'FAIL',error:e.message,checks});}

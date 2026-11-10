(()=>{
const loaders=[];
for(const basis of ['device_id','cli_ip']){
const el=id=>document.getElementById(id+(basis==='cli_ip'?'IP':'')),escape=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let version=0,sessions=[],chosen=0;
function entry(s,selected=false){return `<button class="journey-entry ${selected?'chosen':''}" data-index="${s.index}" aria-label="Select session ${s.index+1}: ${escape(s.title)}"><small>${escape(s.start.slice(0,16))} IST ${s.matched?' · MATCH':''}</small><b>${escape(s.title)}</b><span>${escape(s.video_key)} · ${(s.hours*60).toFixed(2)} estimated min</span><small>Last request: ${escape(s.end.slice(11,19))} · ${escape(s.host)}</small><small>Identity: ${escape(s.identity_sources.map(x=>x==='segment_query'?'direct request':x==='same_cli_manifest'?'manifest-inferred':x).join(', '))}${s.overlap?' · Overlapping activity':''}</small></button>`}
function render(){const sections=[['Previous 5',sessions.slice(Math.max(0,chosen-5),chosen)],['Selected session',[sessions[chosen]]],['Next 5',sessions.slice(chosen+1,chosen+6)]];el('journeyCards').innerHTML=sections.map(([label,items])=>`<article><h3>${label}</h3>${items.length?items.map(s=>entry(s,s.index===chosen)).join(''):'<p class="empty">No further sessions in this filtered period.</p>'}</article>`).join('');el('journeyTimeline').innerHTML=sessions.map(s=>entry(s,s.index===chosen)).join('');el('journeyPosition').textContent=`Session ${chosen+1} of ${sessions.length}`;el('journeyPrevMatch').disabled=!sessions.some(s=>s.index<chosen&&s.matched);el('journeyNextMatch').disabled=!sessions.some(s=>s.index>chosen&&s.matched);}
loaders.push(async input=>{const body={...input,identity_basis:basis};const id=++version;const selected=body.filters?.[basis]||[];const visible=selected.length===1&&typeof selected[0]==='string'&&selected[0].trim()!==''&&selected[0]!=='Unknown';const panel=el('journeyPanel');panel.hidden=!visible;const tile=panel.closest('.layout-tile');if(tile)tile.hidden=!visible;el('journeyContent').hidden=true;if(!visible){sessions=[];return;}el('journeyStatus').textContent='Loading journey…';try{const response=await fetch('/api/journey',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const data=await response.json();if(id!==version)return;if(!response.ok)throw Error(data.error||'Could not load journey');sessions=data.sessions;el('journeyStatus').textContent=data.message+(data.identity_value?` ${data.identity_basis==='cli_ip'?'Client IP':'Device ID'}: ${data.identity_value}. ${sessions.length} observed sessions; ${data.matching_sessions} content matches.`:'');if(!sessions.length){if(data.identity_value)el('journeyStatus').textContent+=' No activity in this selection.';return}chosen=Math.max(0,sessions.findIndex(s=>s.matched));el('journeyContent').hidden=false;render()}catch(e){if(id===version)el('journeyStatus').textContent=e.message}});
el('journeyPanel').addEventListener('click',event=>{const button=event.target.closest('.journey-entry');if(button){chosen=Number(button.dataset.index);render()}});
(()=>{el('journeyPrevMatch').onclick=()=>{const match=sessions.filter(s=>s.matched&&s.index<chosen).at(-1);if(match){chosen=match.index;render()}};el('journeyNextMatch').onclick=()=>{const match=sessions.find(s=>s.matched&&s.index>chosen);if(match){chosen=match.index;render()}}})();


el('journeyExport').onclick=async()=>{
 const button=el('journeyExport');button.disabled=true;
 try{
  if(!applied)throw Error('Select an identifier first');
  const response=await request('/api/journey-export',{...applied,identity_basis:basis});
  const url=URL.createObjectURL(await response.blob()),a=document.createElement('a');
  a.href=url;a.download='smartvod_'+basis+'_journey.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 }catch(e){el('journeyStatus').textContent=e.message}finally{button.disabled=false}
};
}
window.loadJourney=body=>Promise.all(loaders.map(load=>load(body)));
})();

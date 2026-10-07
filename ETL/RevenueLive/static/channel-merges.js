'use strict';
window.ChannelMerges=(()=>{
  const panel=document.createElement('section');panel.className='channel-merge-panel';
  panel.innerHTML='<div class="section-title"><h2>Channel merges</h2><button type="button" id="mergeOpen"><i data-lucide="merge" aria-hidden="true"></i>Merge channels</button></div><div id="mergeList"></div>';
  $('channelDirectory').after(panel);
  const dialog=document.createElement('dialog');dialog.id='mergeDialog';
  dialog.innerHTML='<form id="mergeForm"><h2>Merge channels</h2><label>Find channels<input id="mergeSearch" type="search" placeholder="Search channel names"></label><div class="merge-pickers"><label>Source channel<select id="mergeSource" required></select></label><label>Main channel<select id="mergeTarget" required></select></label></div><button type="button" id="mergePreview">Preview merge</button><div id="mergeReview" hidden><p id="mergeSummary"></p><p>Original uploads and permissions stay unchanged. Different entries on the same date are added together. Users without access to every member retain separate, restricted channels.</p><p id="mergeWarning" role="status"></p><div class="merge-records"><table><thead><tr><th>Date</th><th>Channel</th><th>Views</th><th>Impressions</th><th>Ad revenue</th><th>Sponsorship / others</th><th>Total</th></tr></thead><tbody id="mergeRows"></tbody></table></div><label class="check"><input id="mergeConfirm" type="checkbox">These are separate activities; combine their totals.</label></div><p class="form-error" role="alert"></p><div class="actions"><button type="submit" id="mergeSave" class="primary" disabled>Confirm merge</button><button type="button" id="mergeCancel">Cancel</button></div></form>';
  document.body.append(dialog);
  let plan=null,ticket=0,links=[];
  const selected=new Set();
  $('mergeSearch').parentElement.remove();
  dialog.querySelector('.merge-pickers').innerHTML='<div><span class="field-label">Main channel</span><input id="mergeTarget" type="hidden"><details id="mergeTargetPicker"><summary id="mergeTargetSummary">Choose main channel</summary><div class="merge-menu"><input id="mergeTargetSearch" type="search" placeholder="Search main channel" aria-label="Search main channel"><div id="mergeTargets" class="merge-options"></div></div></details></div><div><span class="field-label">Channels to put under it</span><details id="mergeSourcePicker"><summary id="mergeSourceSummary">Choose channels</summary><div class="merge-menu"><input id="mergeSearch" type="search" placeholder="Search channels" aria-label="Search source channels"><div class="picker-actions"><button type="button" id="mergeSelectShown">Select all</button><button type="button" id="mergeClear">Clear</button></div><div id="mergeSources" class="merge-options" role="group" aria-label="Source channels"></div></div></details></div>';
  for(const id of ['mergeTargetPicker','mergeSourcePicker'])boundedPicker($(id),$(id).querySelector('.merge-menu'));
  const done=document.createElement('button');done.type='button';done.className='merge-picker-done';done.textContent='Done';done.onclick=()=>{$('mergeSourcePicker').open=false;$('mergeSourceSummary').focus();};$('mergeSourcePicker').querySelector('.merge-menu').append(done);
  function closePickers(){for(const id of ['mergeTargetPicker','mergeSourcePicker'])$(id).open=false;}
  dialog.addEventListener('close',closePickers);
  const selection=document.createElement('p');selection.id='mergeSelection';selection.setAttribute('aria-live','polite');dialog.querySelector('.merge-pickers').after(selection);
  function reset(){ticket++;plan=null;$('mergeReview').hidden=true;$('mergeConfirm').checked=false;$('mergeSave').disabled=true;dialog.querySelector('.form-error').textContent='';}
  function candidates(){const search=$('mergeSearch').value.trim().toLowerCase();return directoryChannels.filter(c=>!c.archived&&String(c.id)!==$('mergeTarget').value&&!links.some(r=>r.source_id===c.id||r.target_id===c.id)&&c.name.toLowerCase().includes(search));}
  function options(){
    const target=$('mergeTarget'),previous=target.value;
    const query=$('mergeTargetSearch').value.trim().toLowerCase();
    $('mergeTargets').innerHTML=directoryChannels.filter(c=>!c.archived&&!links.some(r=>r.source_id===c.id)&&c.name.toLowerCase().includes(query)).map(c=>`<button type="button" data-target="${c.id}" aria-pressed="${String(c.id)===previous}">${esc(c.name)}</button>`).join('')||'<p class="muted">No matching channels.</p>';
    $('mergeSources').innerHTML=candidates().map(c=>`<label class="merge-choice"><input type="checkbox" value="${c.id}" ${selected.has(c.id)?'checked':''}><span>${esc(c.name)}</span></label>`).join('')||'<p class="muted">No matching channels.</p>';
    const names=directoryChannels.filter(c=>selected.has(c.id)).map(c=>c.name);
    const main=directoryChannels.find(c=>String(c.id)===target.value);
    $('mergeTargetSummary').textContent=main?.name||'Choose main channel';
    $('mergeSourceSummary').textContent=names.length?`${names.length} channels selected`:'Choose channels';
    $('mergeSelection').textContent=`Main channel: ${main?.name||'Not selected'} | ${names.length} selected${names.length?': '+names.join(', '):''}`;
  }
  $('mergeOpen').onclick=()=>{reset();closePickers();selected.clear();$('mergeTargetSearch').value='';$('mergeTarget').value='';$('mergeSearch').value='';options();dialog.showModal();};
  $('mergeCancel').onclick=()=>{reset();dialog.close();};
  dialog.addEventListener('cancel',reset);
  $('mergeSearch').oninput=options;
  $('mergeTargetSearch').oninput=options;
  $('mergeTargets').onclick=event=>{const button=event.target.closest('[data-target]');if(!button)return;$('mergeTarget').value=button.dataset.target;$('mergeTarget').dispatchEvent(new Event('change'));$('mergeTargetPicker').open=false;$('mergeTargetSummary').focus();};
  $('mergeTarget').onchange=()=>{selected.delete(Number($('mergeTarget').value));reset();options();};
  $('mergeSources').onchange=event=>{const input=event.target;if(input.type!=='checkbox')return;input.checked?selected.add(Number(input.value)):selected.delete(Number(input.value));reset();options();};
  $('mergeSelectShown').onclick=()=>{for(const c of candidates())selected.add(c.id);reset();options();};
  $('mergeClear').onclick=()=>{selected.clear();reset();options();};
  $('mergeConfirm').onchange=()=>{$('mergeSave').disabled=!plan||!!plan.exact_match_dates.length||!$('mergeConfirm').checked;};
  $('mergePreview').onclick=async()=>{
    closePickers();reset();const generation=ticket;$('mergePreview').disabled=true;
    try{
      const data=await api('/api/admin/channel-merges/preview',{method:'POST',body:{sources:[...selected],target:Number($('mergeTarget').value)}});
      if(generation!==ticket)return;plan=data;
      $('mergeSummary').textContent=`Main channel: ${data.target_name}. Adding: ${data.source_channels.map(c=>c.name).join(', ')}. ${data.source_records} source records, ${data.destination_records} existing records, ${data.overlap_dates.length} overlapping dates.${data.existing_channels.length?' Already under this channel: '+data.existing_channels.map(c=>c.name).join(', ')+'.':''}`;
      $('mergeWarning').textContent=data.exact_match_dates.length?`Merge blocked: matching metrics on ${data.exact_match_dates.join(', ')}. Review the original uploads before merging.`:'No exact matching records detected. Review all overlapping entries before confirming.';
      const names=new Map(directoryChannels.map(c=>[c.id,c.name]));
      $('mergeRows').innerHTML=data.rows.map(r=>`<tr><td>${esc(r.day)}</td><td>${esc(names.get(r.channel_id)||r.channel_id)}</td>${['views','impressions','ad','other','total'].map(k=>`<td>${esc(k==='views'||k==='impressions'?number(r[k]):money(r[k]))}</td>`).join('')}</tr>`).join('');
      $('mergeReview').hidden=false;
    }catch(e){if(generation===ticket)dialog.querySelector('.form-error').textContent=e.message;}finally{$('mergePreview').disabled=false;}
  };
  $('mergeForm').onsubmit=async event=>{
    event.preventDefault();if(!plan||!$('mergeConfirm').checked)return;$('mergeSave').disabled=true;
    try{await api('/api/admin/channel-merges',{method:'POST',body:{sources:plan.sources,target:plan.target,token:plan.token,confirm_sum:true}});dialog.close();reset();await syncAccess();await loadUsers();notify('Channels merged for reporting. Original data and permissions retained.');}
    catch(e){dialog.querySelector('.form-error').textContent=e.message;$('mergeSave').disabled=false;}
  };
  async function load(){
    try{const data=await api('/api/admin/channel-merges');links=data.rows;$('mergeList').innerHTML=data.rows.map(r=>`<div class="merge-link"><span>${esc(r.source_name)} <strong>under ${esc(r.target_name)}</strong></span><button type="button" data-undo-merge="${r.source_id}">Undo merge</button></div>`).join('')||'<p class="muted">No merged channels.</p>';window.lucide?.createIcons();}
    catch(e){$('mergeList').textContent=e.message;}
  }
  $('mergeList').onclick=async event=>{const button=event.target.closest('[data-undo-merge]');if(!button||!confirm('Restore separate channel reporting? Original data and assignments will stay unchanged.'))return;button.disabled=true;try{await api('/api/admin/channel-merges/'+button.dataset.undoMerge,{method:'DELETE'});await syncAccess();await loadUsers();notify('Merge undone.');}catch(e){notify(e.message);button.disabled=false;}};
  function clear(){reset();selected.clear();links=[];dialog.close();$('mergeRows').replaceChildren();$('mergeSources').replaceChildren();$('mergeSelection').textContent='';$('mergeList').replaceChildren();}
  return {load,clear};
})();

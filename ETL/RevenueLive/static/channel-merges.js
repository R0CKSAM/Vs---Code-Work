'use strict';
window.ChannelMerges=(()=>{
  const panel=document.createElement('section');panel.className='channel-merge-panel';
  panel.innerHTML='<div class="section-title"><h2>Channel merges</h2><button type="button" id="mergeOpen"><i data-lucide="merge" aria-hidden="true"></i>Merge channels</button></div><div id="mergeList"></div>';
  $('channelDirectory').after(panel);
  const dialog=document.createElement('dialog');dialog.id='mergeDialog';
  dialog.innerHTML='<form id="mergeForm"><h2>Merge channels</h2><label>Find channels<input id="mergeSearch" type="search" placeholder="Search channel names"></label><div class="merge-pickers"><label>Source channel<select id="mergeSource" required></select></label><label>Main channel<select id="mergeTarget" required></select></label></div><button type="button" id="mergePreview">Preview merge</button><div id="mergeReview" hidden><p id="mergeSummary"></p><p>Original uploads and permissions stay unchanged. Different entries on the same date are added together. Users without access to every member retain separate, restricted channels.</p><p id="mergeWarning" role="status"></p><div class="merge-records"><table><thead><tr><th>Date</th><th>Channel</th><th>Views</th><th>Impressions</th><th>Ad revenue</th><th>Sponsorship / others</th><th>Total</th></tr></thead><tbody id="mergeRows"></tbody></table></div><label class="check"><input id="mergeConfirm" type="checkbox">These are separate activities; combine their totals.</label></div><p class="form-error" role="alert"></p><div class="actions"><button type="submit" id="mergeSave" class="primary" disabled>Confirm merge</button><button type="button" id="mergeCancel">Cancel</button></div></form>';
  document.body.append(dialog);
  let plan=null,ticket=0;
  function reset(){ticket++;plan=null;$('mergeReview').hidden=true;$('mergeConfirm').checked=false;$('mergeSave').disabled=true;dialog.querySelector('.form-error').textContent='';}
  function options(){const search=$('mergeSearch').value.toLowerCase();for(const id of ['mergeSource','mergeTarget']){const select=$(id),previous=select.value;select.replaceChildren(new Option('Choose channel',''));for(const c of directoryChannels.filter(c=>!c.archived&&(c.name.toLowerCase().includes(search)||String(c.id)===previous)))select.add(new Option(c.name,c.id));select.value=previous;}}
  $('mergeOpen').onclick=()=>{reset();$('mergeSearch').value='';options();dialog.showModal();};
  $('mergeCancel').onclick=()=>{reset();dialog.close();};
  dialog.addEventListener('cancel',reset);
  $('mergeSearch').oninput=options;
  for(const id of ['mergeSource','mergeTarget'])$(id).onchange=reset;
  $('mergeConfirm').onchange=()=>{$('mergeSave').disabled=!plan||!!plan.exact_match_dates.length||!$('mergeConfirm').checked;};
  $('mergePreview').onclick=async()=>{
    reset();const generation=ticket;$('mergePreview').disabled=true;
    try{
      const data=await api('/api/admin/channel-merges/preview',{method:'POST',body:{source:Number($('mergeSource').value),target:Number($('mergeTarget').value)}});
      if(generation!==ticket)return;plan=data;
      $('mergeSummary').textContent=`${data.source_name} to ${data.target_name}: ${data.source_records} source records, ${data.destination_records} destination records, ${data.overlap_dates.length} overlapping dates.`;
      $('mergeWarning').textContent=data.exact_match_dates.length?`Merge blocked: matching metrics on ${data.exact_match_dates.join(', ')}. Review the original uploads before merging.`:'No exact matching records detected. Review all overlapping entries before confirming.';
      const names=new Map(directoryChannels.map(c=>[c.id,c.name]));
      $('mergeRows').innerHTML=data.rows.map(r=>`<tr><td>${esc(r.day)}</td><td>${esc(names.get(r.channel_id)||r.channel_id)}</td>${['views','impressions','ad','other','total'].map(k=>`<td>${esc(k==='views'||k==='impressions'?number(r[k]):money(r[k]))}</td>`).join('')}</tr>`).join('');
      $('mergeReview').hidden=false;
    }catch(e){if(generation===ticket)dialog.querySelector('.form-error').textContent=e.message;}finally{$('mergePreview').disabled=false;}
  };
  $('mergeForm').onsubmit=async event=>{
    event.preventDefault();if(!plan||!$('mergeConfirm').checked)return;$('mergeSave').disabled=true;
    try{await api('/api/admin/channel-merges',{method:'POST',body:{source:plan.source,target:plan.target,token:plan.token,confirm_sum:true}});dialog.close();reset();await syncAccess();await loadUsers();notify('Channels merged for reporting. Original data and permissions retained.');}
    catch(e){dialog.querySelector('.form-error').textContent=e.message;$('mergeSave').disabled=false;}
  };
  async function load(){
    try{const data=await api('/api/admin/channel-merges');$('mergeList').innerHTML=data.rows.map(r=>`<div class="merge-link"><span>${esc(r.source_name)} <strong>under ${esc(r.target_name)}</strong></span><button type="button" data-undo-merge="${r.source_id}">Undo merge</button></div>`).join('')||'<p class="muted">No merged channels.</p>';window.lucide?.createIcons();}
    catch(e){$('mergeList').textContent=e.message;}
  }
  $('mergeList').onclick=async event=>{const button=event.target.closest('[data-undo-merge]');if(!button||!confirm('Restore separate channel reporting? Original data and assignments will stay unchanged.'))return;button.disabled=true;try{await api('/api/admin/channel-merges/'+button.dataset.undoMerge,{method:'DELETE'});await syncAccess();await loadUsers();notify('Merge undone.');}catch(e){notify(e.message);button.disabled=false;}};
  function clear(){reset();dialog.close();$('mergeRows').replaceChildren();$('mergeList').replaceChildren();}
  return {load,clear};
})();

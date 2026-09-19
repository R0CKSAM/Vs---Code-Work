"""Searchable channel selection for the War Room."""

import json

from .parser import DAVIS_CUP_MENU_TARGETS

SCRIPT = r"""
let channelSelection=new Set(['__all__']),channelKeys=[],selectionRevision=0,selectionBusy=false;
let stateTag='',stateUrl='',stateData=null,renderedRevision=-1;
let selectionTimer=null;
const davisCupFeedKeys=new Set(__DAVIS_CUP_FEED_KEYS__);
function channelDisplayName(key){return key==='__all__'?'All channels':davisCupFeedKeys.has(key)?'Davis Cup ('+key+')':key}
const channelNameOrder=new Intl.Collator('en',{sensitivity:'base',numeric:true});
function compareChannelKeys(a,b){
 if(a==='__all__')return b==='__all__'?0:-1;
 if(b==='__all__')return 1;
 return channelNameOrder.compare(channelDisplayName(a),channelDisplayName(b))||a.localeCompare(b);
}
const nativeTarget=$('target');nativeTarget.closest('label').hidden=true;
const channelPicker=document.createElement('details');channelPicker.className='channel-picker';
channelPicker.innerHTML='<summary id="channelSummary">Channel: All channels</summary><div class="channel-menu"><input id="channelSearch" type="search" placeholder="Search channels or matches" aria-label="Search channels"><div class="channel-actions"><button type="button" id="allChannels">All channels</button><button type="button" id="selectVisibleChannels">Select visible</button><button type="button" id="clearChannels">Clear</button></div><div id="channelOptions"></div></div>';
nativeTarget.closest('label').after(channelPicker);
function visibleChannelKeys(){const q=$('channelSearch').value.trim().toLowerCase();return channelKeys.filter(k=>k!=='__all__'&&channelDisplayName(k).toLowerCase().includes(q))}
function paintChannelPicker(){
 $('channelSummary').textContent='Channel: '+(channelSelection.has('__all__')?'All channels':channelSelection.size===1?channelDisplayName([...channelSelection][0]):channelSelection.size+' selected');
 $('channelOptions').replaceChildren();
 for(const key of visibleChannelKeys()){const label=document.createElement('label'),check=document.createElement('input'),text=document.createElement('span');check.type='checkbox';check.checked=channelSelection.has('__all__')||channelSelection.has(key);text.textContent=channelDisplayName(key);label.append(check,text);check.onchange=()=>{if(channelSelection.has('__all__'))channelSelection=new Set(channelKeys.filter(k=>k!=='__all__'));check.checked?channelSelection.add(key):channelSelection.delete(key);changeChannels()};$('channelOptions').append(label)}
}
function changeChannels(){selectionRevision++;paintChannelPicker();clearTimeout(selectionTimer);selectionTimer=setTimeout(()=>{selectionTimer=null;refresh()},180)}
function selectedStateKey(){
 const available=channelKeys.filter(k=>k!=='__all__');
 if(channelSelection.has('__all__')||available.length&&available.every(k=>channelSelection.has(k)))return '__all__';
 return channelSelection.size===1?[...channelSelection][0]:'__selection__';
}
$('channelSearch').oninput=paintChannelPicker;
$('allChannels').onclick=()=>{channelSelection=new Set(['__all__']);changeChannels()};
$('selectVisibleChannels').onclick=()=>{if(channelSelection.has('__all__'))channelSelection.clear();visibleChannelKeys().forEach(k=>channelSelection.add(k));changeChannels()};
$('clearChannels').onclick=()=>{channelSelection.clear();changeChannels()};
document.addEventListener('click',event=>{if(!channelPicker.contains(event.target))channelPicker.open=false});
document.addEventListener('keydown',event=>{if(event.key==='Escape')channelPicker.open=false});
refresh=async function(){
 if(selectionBusy||selectionTimer)return;selectionBusy=true;const revision=selectionRevision;
 try{
  let key=selectedStateKey();
  const url='/api/state?channel='+encodeURIComponent(key),headers={};if(stateUrl===url&&stateTag)headers['If-None-Match']=stateTag;
  const response=await fetch(url,{cache:'no-store',headers,signal:AbortSignal.timeout(15000)});
  if(response.status===304&&revision===renderedRevision)return;
  if(response.status!==304&&!response.ok)throw Error('Dashboard unavailable');
  if(response.status!==304){stateData=await response.json();stateTag=response.headers.get('ETag')||'';stateUrl=url}
  const next=structuredClone(stateData);channelKeys=[...new Set(['__all__',...(next.channels||Object.keys(next.series||{})),...(next.scheduled_targets||[])])].sort(compareChannelKeys);
  if(key==='__selection__'&&channelSelection.size>1){
   $('channelSummary').textContent='Channel: Calculating selection...';
   const query=new URLSearchParams;channelSelection.forEach(k=>query.append('channel',k));
   const result=await fetch('/api/selection?'+query,{cache:'no-store',signal:AbortSignal.timeout(45000)});if(!result.ok)throw Error('Selected-channel totals unavailable');
   const combined=await result.json();for(const field of ['series','summaries','breakdowns'])next[field][key]=combined[field]?.[key]||(field==='series'?[]:{});
  }else if(!channelSelection.size){next.series[key]=[];next.summaries[key]={};next.breakdowns[key]={}}
  if(revision!==selectionRevision)return;
  next.selected_channels=[...channelSelection];data=next;nativeTarget.replaceChildren();const option=document.createElement('option');option.value=key;option.textContent=channelDisplayName(key);nativeTarget.append(option);nativeTarget.value=key;
  paintChannelPicker();updateRangeBounds();render();renderedRevision=revision;
  if(!channelSelection.size||!(data.series[key]||[]).length)$('visibleRange').textContent=channelSelection.size?'No processed requests for this selection in the live window':'No channels selected';
 }catch(error){$('sourceStatus').textContent='SELECTION UNAVAILABLE';$('sourceSub').textContent=error.message}
 finally{selectionBusy=false;if(revision!==selectionRevision)refresh()}
};
"""
SCRIPT = SCRIPT.replace('__DAVIS_CUP_FEED_KEYS__', json.dumps(DAVIS_CUP_MENU_TARGETS))

STYLE = """
.toolbar label[hidden]{display:none!important}
.channel-picker{position:relative;min-width:0;width:280px;max-width:100%;z-index:15;flex-shrink:1}
.channel-picker summary{cursor:pointer;padding:7px 10px;border:1px solid var(--line);background:var(--panel);overflow-wrap:anywhere}
.channel-menu{position:absolute;top:100%;left:0;width:min(440px,90vw);padding:10px;background:var(--panel);border:1px solid var(--line);box-shadow:0 8px 25px #0008}
.channel-menu input[type=search]{width:100%;min-width:0;padding:8px;background:var(--bg);color:var(--text);border:1px solid var(--line)}.channel-actions{display:flex;gap:5px;flex-wrap:wrap;margin:8px 0}
#channelOptions{max-height:320px;overflow-y:auto}#channelOptions label{display:flex;gap:8px;align-items:center;padding:7px;white-space:normal;overflow-wrap:anywhere}
#channelOptions input{width:16px;height:16px;flex:0 0 16px}
"""

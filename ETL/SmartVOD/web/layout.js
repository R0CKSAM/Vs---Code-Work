/* Native responsive layout editor. No analytics data or filters are stored here. */
(()=>{
 const root=document.getElementById('results'),key='smartvod.panelLayout.v1';
 const toolbar=document.createElement('div');toolbar.className='layout-toolbar';
 toolbar.innerHTML='<button id="layoutToggle" aria-pressed="false">Edit layout</button><button id="layoutReset">Reset layout</button><span id="layoutSaveStatus" role="status"></span>';
 document.querySelector('.drawer-tools').append(toolbar);
 const editBar=document.createElement('div');editBar.className='layout-edit-bar';editBar.hidden=true;
 editBar.innerHTML='<span id="layoutHelp">Drag a panel title to move. Right edge: width. Bottom edge: height. Corner: both. Changes save automatically.</span><button id="layoutDone" class="primary">Done editing</button>';
 root.before(editBar);
 let saved={},editing=false,gesture=null,saveTimer;
 try{const value=JSON.parse(localStorage.getItem(key)||'{}');if(value&&typeof value==='object'&&!Array.isArray(value))saved=value}catch{}
 const defaults={},tiles=new Map();
 const toggle=document.getElementById('layoutToggle'),reset=document.getElementById('layoutReset'),status=document.getElementById('layoutSaveStatus');
 const editStatus=document.createElement('span');editStatus.className='layout-edit-status';editStatus.setAttribute('role','status');editBar.insertBefore(editStatus,document.getElementById('layoutDone'));
 new MutationObserver(()=>{editStatus.textContent=status.textContent}).observe(status,{childList:true,characterData:true,subtree:true});
 function valid(v){return v&&Number.isInteger(v.order)&&v.order>=0&&v.order<100&&Number.isInteger(v.width)&&v.width>=3&&v.width<=12&&Number.isInteger(v.height)&&v.height>=0&&v.height<=1800}
 function config(id){return valid(saved[id])?saved[id]:defaults[id]}
 function apply(tile){const c=config(tile.dataset.layoutId);tile.style.order=c.order;tile.style.setProperty('--tile-span',c.width);tile.style.setProperty('--tile-height',c.height?c.height+'px':'auto');tile.querySelector('.layout-handle').setAttribute('aria-label',tile.dataset.layoutLabel+'. Drag to move; arrow keys move, Shift plus arrow keys resize.')}
 function persist(){try{const data={};for(const id of tiles.keys())data[id]={...config(id)};localStorage.setItem(key,JSON.stringify(data));status.textContent='Layout saved in this browser'}catch{status.textContent='Cannot save in this browser; layout works for this visit.'}}
 function changed(){clearTimeout(saveTimer);saveTimer=setTimeout(persist,180)}
 function ordered(){return [...tiles.values()].filter(t=>t.isConnected).sort((a,b)=>config(a.dataset.layoutId).order-config(b.dataset.layoutId).order)}
 function reorder(source,target,after){const list=ordered().filter(t=>t!==source),index=list.indexOf(target);list.splice(index+(after?1:0),0,source);list.forEach((tile,i)=>{saved[tile.dataset.layoutId]={...config(tile.dataset.layoutId),order:i};apply(tile)});changed()}
 function add(node,id,label,width){
  if(node.parentElement.classList.contains('layout-tile'))return;
  const tile=document.createElement('div');tile.className='layout-tile';tile.dataset.layoutId=id;tile.dataset.layoutLabel=label;tile.hidden=node.hidden;
  const sequence=['kpi-0','kpi-1','kpi-2','kpi-3','average-0','average-1','chart-0','chart-1','devicePanel','ipPanel','journeyPanel','journeyPanelIP','breakdown-0','breakdown-1','breakdown-2','breakdown-3','content'];
  defaults[id]??={order:sequence.indexOf(id),width,height:0};
  node.before(tile);tile.append(node);node.classList.add('layout-content');
  const handle=document.createElement('button');handle.className='layout-handle';handle.type='button';handle.textContent=label;handle.title='Drag to move. Arrow keys move. Shift + arrows resize.';
  tile.prepend(handle);tiles.set(id,tile);
  for(const [axis,description] of [['x','width'],['y','height'],['both','width and height']]){
   const grip=document.createElement('button');grip.className='layout-resize layout-resize-'+axis;grip.type='button';grip.dataset.axis=axis;grip.setAttribute('aria-label','Resize '+label+' '+description);grip.title='Drag to resize '+description+'; arrow keys resize; double-click restores default size';tile.append(grip);
   grip.addEventListener('pointerdown',e=>start(e,tile,'resize-'+axis));
   grip.addEventListener('keydown',e=>keyboard(e,tile,'resize-'+axis));
   grip.addEventListener('dblclick',()=>{const c={...config(id)};if(axis!=='y')c.width=defaults[id].width;if(axis!=='x')c.height=0;saved[id]=c;apply(tile);changed()});
  }
  apply(tile);fitObserver.observe(tile);
  handle.addEventListener('pointerdown',e=>start(e,tile,'move'));
  handle.addEventListener('keydown',e=>keyboard(e,tile,e.shiftKey?'resize-both':'move'));
 }
 function discover(){
  [...root.querySelectorAll('.kpis>article')].forEach((n,i)=>add(n,'kpi-'+i,n.querySelector('label').textContent.trim().replace(/[^\w\s]/g,''),3));
  [...root.querySelectorAll('.average-pair>article')].forEach((n,i)=>add(n,'average-'+i,i?'Average minutes / Client IP':'Average minutes / Device ID',6));
  [...root.querySelectorAll('.chart-grid>article')].forEach((n,i)=>add(n,'chart-'+i,i?'Delivery snapshot':'Watch time by hour',i?4:8));
  for(const [id,label] of [['devicePanel','Device explorer'],['ipPanel','Client IP explorer'],['journeyPanel','Device ID journey'],['journeyPanelIP','Client IP journey']]){const node=document.getElementById(id);add(node,id,label,id.startsWith('journey')?12:6)}
  [...root.querySelectorAll('#breakdowns>article')].forEach((n,i)=>add(n,'breakdown-'+i,n.querySelector('h3').firstChild.textContent,3));
  const content=[...root.children].find(n=>n.matches('section.panel')&&!n.id);if(content)add(content,'content','Content performance',12);
 }
 function keyboard(e,tile,mode){
  if(!editing||!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key))return;e.preventDefault();
  if(mode==='move'){const list=ordered(),at=list.indexOf(tile),delta=['ArrowLeft','ArrowUp'].includes(e.key)?-1:1,target=list[at+delta];if(target)reorder(tile,target,delta>0)}
  else{const c={...config(tile.dataset.layoutId)};if(mode!=='resize-y'&&e.key==='ArrowLeft')c.width=Math.max(3,c.width-1);if(mode!=='resize-y'&&e.key==='ArrowRight')c.width=Math.min(12,c.width+1);if(mode!=='resize-x'&&e.key==='ArrowUp')c.height=Math.max(140,(c.height||tile.offsetHeight)-40);if(mode!=='resize-x'&&e.key==='ArrowDown')c.height=Math.min(1800,(c.height||tile.offsetHeight)+40);saved[tile.dataset.layoutId]=c;apply(tile);changed()}
 }
 function start(e,tile,mode){if(!editing||e.button!==0)return;e.preventDefault();gesture={tile,mode,x:e.clientX,y:e.clientY,width:tile.offsetWidth,height:tile.offsetHeight,config:{...config(tile.dataset.layoutId)},moved:false};e.currentTarget.setPointerCapture(e.pointerId);tile.classList.add('layout-active')}
 document.addEventListener('pointermove',e=>{
  if(!gesture)return;const g=gesture,dx=e.clientX-g.x,dy=e.clientY-g.y;if(Math.abs(dx)+Math.abs(dy)<5&&!g.moved)return;g.moved=true;
  if(g.mode.startsWith('resize')){const gap=parseFloat(getComputedStyle(root).columnGap)||16,unit=(root.clientWidth-11*gap)/12;const width=g.mode==='resize-y'?g.config.width:Math.max(3,Math.min(12,Math.round((g.width+dx+gap)/(unit+gap))));const height=g.mode==='resize-x'?g.config.height:Math.max(140,Math.min(1800,Math.round(g.height+dy)));saved[g.tile.dataset.layoutId]={...g.config,width,height};apply(g.tile)}
  else{const target=document.elementFromPoint(e.clientX,e.clientY)?.closest('.layout-tile');document.querySelectorAll('.layout-drop').forEach(t=>t.classList.remove('layout-drop'));if(target&&target!==g.tile){g.target=target;const rect=target.getBoundingClientRect();g.after=e.clientY>rect.y+rect.height/2;target.classList.add('layout-drop')}else g.target=null;
   if(e.clientY>innerHeight-65)window.scrollBy(0,18);else if(e.clientY<100)window.scrollBy(0,-18);
  }
 });
 function finish(cancel=false){if(!gesture)return;const g=gesture;gesture=null;g.tile.classList.remove('layout-active');document.querySelectorAll('.layout-drop').forEach(t=>t.classList.remove('layout-drop'));if(cancel){saved[g.tile.dataset.layoutId]=g.config;apply(g.tile)}else if(g.moved){if(g.mode==='move'&&g.target)reorder(g.tile,g.target,g.after);else if(g.mode.startsWith('resize'))changed()}}
 document.addEventListener('pointerup',()=>finish());document.addEventListener('pointercancel',()=>finish(true));
 document.addEventListener('keydown',e=>{if(e.key==='Escape'&&gesture){finish(true);e.preventDefault()}});
 function setEditing(value){finish();editing=value;root.classList.toggle('layout-editing',editing);toggle.setAttribute('aria-pressed',editing);toggle.textContent=editing?'Finish layout editing':'Edit layout';editBar.hidden=!editing;if(editing){closeAdvanced();requestAnimationFrame(()=>{document.getElementById('layoutDone').focus({preventScroll:true})})}else{persist();if(!document.body.classList.contains('drawer-open'))document.getElementById('advancedToggle').focus({preventScroll:true})}}
 toggle.onclick=()=>setEditing(!editing);document.getElementById('layoutDone').onclick=()=>setEditing(false);
 reset.onclick=()=>{finish(true);saved={};for(const tile of tiles.values())apply(tile);clearTimeout(saveTimer);try{localStorage.removeItem(key);status.textContent='Default layout restored'}catch{status.textContent='Default layout restored for this visit'}};
 let fitFrame;
 function fitKpis(){cancelAnimationFrame(fitFrame);fitFrame=requestAnimationFrame(()=>{
  for(const tile of tiles.values()){
   const card=tile.querySelector('article'),number=tile.querySelector('[id]');if(!tile.dataset.layoutId.startsWith('kpi-')||!card||!number)continue;
   const maximum=innerWidth<=450?30:42;number.style.fontSize=maximum+'px';
   for(let size=maximum;size>18&&(number.scrollWidth>number.clientWidth+1||card.scrollHeight>card.clientHeight+1);size--)number.style.fontSize=(size-1)+'px';
  }
 })}
 const fitObserver=new ResizeObserver(fitKpis);
 new MutationObserver(fitKpis).observe(root.querySelector('.kpis'),{childList:true,characterData:true,subtree:true});
 new MutationObserver(discover).observe(document.getElementById('breakdowns'),{childList:true});discover();root.classList.add('layout-grid');
})();

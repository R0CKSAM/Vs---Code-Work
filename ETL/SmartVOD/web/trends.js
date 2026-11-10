/* Filter-scoped watch-hour charts; no third-party scripts or data requests. */
(()=>{
 const palette=['#10845b','#3278c3','#9758bb','#be6632','#178c96','#b24171','#687e22','#6456b8','#865b40','#537488'];
 const colorFor=i=>palette[i]||`hsl(${(i*137.508)%360} 55% 38%)`;
 const preferences={watch:'compare'},hiddenSeries=new Map(),observed=new Set(),widths=new WeakMap(),models=new Map();let latest,frame,expandedKey=null,opener=null;
 const titles={watch:'Watch time by hour',device_type:'Device type',os:'Operating system',region:'Region',isp:'Internet provider'};
 const dialog=document.createElement('dialog');dialog.className='chart-dialog';dialog.setAttribute('aria-labelledby','expandedChartTitle');
 dialog.innerHTML='<div class="chart-dialog-header"><div><h2 id="expandedChartTitle"></h2><p id="expandedChartScope"></p></div><button type="button" id="closeExpandedChart">Close chart</button></div><div id="expandedChartBody"></div>';
 document.body.append(dialog);const expandedBody=dialog.querySelector('#expandedChartBody');
 function closeExpanded(){if(!dialog.open)return;dialog.close();expandedKey=null;document.body.classList.remove('chart-expanded');const button=opener?.isConnected?opener:[...document.querySelectorAll('[data-expand-chart]')].find(b=>b.dataset.expandChart===dialog.dataset.chart);button?.focus({preventScroll:true})}
 dialog.querySelector('#closeExpandedChart').onclick=closeExpanded;dialog.addEventListener('cancel',e=>{e.preventDefault();closeExpanded()});
 dialog.addEventListener('keydown',e=>{if(e.key!=='Tab')return;const nodes=[...dialog.querySelectorAll('button,[tabindex="0"]')].filter(n=>!n.disabled&&n.getClientRects().length);const first=nodes[0],last=nodes.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus()}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus()}});
 dialog.addEventListener('click',e=>{if(e.target===dialog){const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)closeExpanded()}});
 function addExpand(root,key){const button=document.createElement('button');button.type='button';button.className='expand-chart';button.dataset.expandChart=key;button.textContent='Expand';button.setAttribute('aria-label','Expand '+titles[key]+' chart');button.onclick=()=>{opener=button;expandedKey=key;dialog.dataset.chart=key;dialog.showModal();document.body.classList.add('chart-expanded');renderExpanded();dialog.querySelector('#closeExpandedChart').focus()};root.querySelector('.trend-controls').append(button)}
 function renderExpanded(){if(!expandedKey||!latest)return;const priorScroll=expandedBody.querySelector('.trend-viewport')?.scrollLeft||0,priorBodyScroll=expandedBody.scrollTop;expandedBody.replaceChildren();dialog.querySelector('#expandedChartTitle').textContent=titles[expandedKey];dialog.querySelector('#expandedChartScope').textContent=typeof applied!=='undefined'&&applied?`${applied.start} to ${applied.end} / ${applied.timeStart}-${applied.timeEnd} IST / applied filters`:'Applied selection / IST';const watch=expandedKey==='watch';const mode=watch?preferences.watch:preferences[expandedKey]||'daily';pickMode(expandedBody,watch?[['compare','Compare days'],['continuous','Continuous']]:[['totals','Totals'],['daily',latest.trend_dates.length>1?'Daily trend':'Hourly trend'],['continuous','Hourly timeline']],mode,value=>{preferences[expandedKey]=value;redraw()});if(!watch&&mode==='totals'){drawTotals(expandedBody,expandedKey);return}const model=models.get(watch?(mode==='continuous'?'watch-continuous':'watch'):expandedKey);if(model)draw(expandedBody,{...model,expanded:true});const plot=expandedBody.querySelector('.trend-viewport');if(plot)plot.scrollLeft=priorScroll;expandedBody.scrollTop=priorBodyScroll}
 function drawTotals(root,field){const rows=latest.breakdown[field]||[],max=Math.max(...rows.map(r=>r.hours),1);const plot=document.createElement('div');plot.className='expanded-totals';plot.setAttribute('aria-label','Top five total estimated watch hours');plot.innerHTML=rows.length?rows.map((r,i)=>`<div class="expanded-total-row"><div><span>${esc(r.label)}</span><b>${fmt(r.hours,3)} h</b></div><div class="expanded-total-track"><i style="width:${r.hours/max*100}%;background:${colorFor(i)}"></i></div></div>`).join(''):'<p class="empty">No matching activity in this selection.</p>';root.append(plot)}
 const dateLabel=day=>new Date(day+'T00:00:00Z').toLocaleDateString('en-GB',{day:'2-digit',month:'short',timeZone:'UTC'});
 function hours(){return Array.from({length:24},(_,i)=>String(i).padStart(2,'0'))}
 function ticks(days,continuous=false){return continuous?days.flatMap(day=>hours().map(hour=>({day,hour,label:dateLabel(day)+' '+hour+':00'}))):days.map(day=>({day,label:dateLabel(day)}))}
 function pickMode(root,items,current,callback){const bar=document.createElement('div');bar.className='trend-controls';bar.setAttribute('role','group');bar.setAttribute('aria-label','Chart view');for(const [value,label] of items){const button=document.createElement('button');button.type='button';button.textContent=label;button.dataset.mode=value;button.setAttribute('aria-pressed',String(value===current));button.onclick=()=>{const owner=root.closest('.breakdown')||root;callback(value);owner.querySelector(`[data-mode="${value}"]`)?.focus({preventScroll:true})};bar.append(button)}root.append(bar)}
 function draw(root,{id,labels,series,continuous=false,caption,expanded=false}){
  if(!expanded)models.set(id,{id,labels,series,continuous,caption});
  const hidden=hiddenSeries.get(id)||new Set();hiddenSeries.set(id,hidden);
  const legend=document.createElement('div');legend.className='trend-legend';legend.setAttribute('aria-label','Toggle chart lines');
  legend.dataset.chart=id;
  series.forEach((s,i)=>{const button=document.createElement('button');button.type='button';button.title=s.name;button.setAttribute('aria-pressed',String(!hidden.has(s.name)));const swatch=document.createElement('i');swatch.style.background=colorFor(i);const name=document.createElement('span');name.textContent=s.name;button.append(swatch,name);button.onclick=()=>{hidden.has(s.name)?hidden.delete(s.name):hidden.add(s.name);redraw();[...(expanded?expandedBody:document).querySelectorAll('.trend-legend')].find(n=>n.dataset.chart===id)?.querySelectorAll('button')[i]?.focus({preventScroll:true})};legend.append(button)});
  root.append(legend);
  if(hidden.size){const restore=document.createElement('button');restore.type='button';restore.className='restore-chart-lines';restore.textContent='Show all lines';restore.onclick=()=>{hidden.clear();redraw();[...(expanded?expandedBody:document).querySelectorAll('.trend-legend')].find(n=>n.dataset.chart===id)?.querySelector('button')?.focus({preventScroll:true})};root.append(restore)}
  const active=series.map((s,i)=>({...s,color:colorFor(i)})).filter(s=>!hidden.has(s.name));
  if(!labels.length||!series.length){const empty=document.createElement('p');empty.className='empty';empty.textContent='No matching activity in this selection.';root.append(empty);return}
  const viewport=document.createElement('div');viewport.className='trend-viewport';viewport.tabIndex=0;viewport.setAttribute('aria-label',continuous?'Continuous hourly chart. Scroll horizontally for later dates.':'Watch-hour trend chart');
  if(!active.length){const note=document.createElement('p');note.className='empty';note.textContent='All lines are hidden. Use Show all lines or select a legend label.';root.append(note);return}
  const H=expanded?Math.max(220,Math.min(620,innerHeight-290)):238,L=expanded?64:48,R=20,T=18,B=H-50;
  root.style.setProperty('--trend-height',H+'px');root.style.setProperty('--trend-axis-width',L-2+'px');
  const style=getComputedStyle(root),plotWidth=root.clientWidth-parseFloat(style.paddingLeft)-parseFloat(style.paddingRight);
  const W=continuous?Math.max(plotWidth-8,labels.length*Math.max(12,(plotWidth-L-24)/23)+L+16):Math.max(plotWidth-8,250);
  const max=Math.max(...active.flatMap(s=>s.values.filter(v=>v!==null)),1),x=i=>L+i*(W-L-R)/Math.max(labels.length-1,1),y=v=>B-v/max*(B-T);
  let svg=`<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(caption)}"><title>${esc(caption)}</title>`;
  let axis='<div class="trend-y-axis" aria-hidden="true">';
  for(let i=0;i<=4;i++){const yy=B-i*(B-T)/4;svg+=`<line x1="${L}" x2="${W-R}" y1="${yy}" y2="${yy}" stroke="#dce7df"/>`;axis+=`<span style="top:${yy-7}px">${fmt(max*i/4,1)}</span>`}axis+='</div>';
  if(continuous)labels.forEach((label,i)=>{if(i%24===0){svg+=`<line x1="${x(i)}" x2="${x(i)}" y1="${T}" y2="${B}" stroke="#a7bfb0" stroke-dasharray="3 4"/><text x="${x(i)+3}" y="${H-8}">${esc(dateLabel(label.day))}</text>`}});
  const every=continuous?6:Math.max(1,Math.ceil(labels.length/Math.max(3,Math.floor((W-L-R)/72))));
  labels.forEach((label,i)=>{if(i%every===0||i===labels.length-1)svg+=`<text x="${x(i)}" y="${H-30}" text-anchor="${i===0?'start':i===labels.length-1?'end':'middle'}">${esc(label.hour?label.hour+':00':label.label)}</text>`});
  active.forEach(s=>{let path='',open=false;s.values.forEach((value,i)=>{if(value===null){open=false;return}path+=(open?' L':' M')+x(i)+','+y(value);open=true});svg+=`<path class="trend-line" data-series="${esc(s.name)}" d="${path}" fill="none" stroke="${s.color}" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>`;s.values.forEach((value,i)=>{if(value!==null)svg+=`<circle cx="${x(i)}" cy="${y(value)}" r="${continuous?2:3}" fill="${s.color}"><title>${esc(s.name)} / ${esc(labels[i].label)}: ${fmt(value,3)} h</title></circle>`})});
  svg+=`<line class="trend-cursor" y1="18" y2="${B}" stroke="#607969" stroke-dasharray="3 3" visibility="hidden"/></svg>`;
  viewport.innerHTML=axis+svg;root.append(viewport);const tip=document.createElement('div');tip.className='trend-tooltip';tip.hidden=true;root.append(tip);
  let inspected=0;
  function inspect(clientX){const rect=viewport.querySelector('svg').getBoundingClientRect(),at=Math.max(0,Math.min(labels.length-1,Math.round((clientX-rect.left-L)/(W-L-R)*Math.max(labels.length-1,1))));inspected=at;const cursor=viewport.querySelector('.trend-cursor');cursor.setAttribute('x1',x(at));cursor.setAttribute('x2',x(at));cursor.setAttribute('visibility','visible');tip.hidden=false;tip.innerHTML=`<strong>${esc(labels[at].label)} IST</strong>`+active.map(s=>`<div><span>${esc(s.name)}</span><b>${s.values[at]===null?'Not loaded':fmt(s.values[at],3)+' h'}</b></div>`).join('');const bounds=root.getBoundingClientRect(),tipWidth=Math.min(expanded?440:320,root.clientWidth-8);tip.style.width=tipWidth+'px';tip.style.left=Math.max(0,Math.min(clientX-bounds.left+12,root.clientWidth-tipWidth-8))+'px';tip.style.top=Math.max(0,viewport.offsetTop+12)+'px'}
  viewport.addEventListener('keydown',e=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();inspected=e.key==='Home'?0:e.key==='End'?labels.length-1:Math.max(0,Math.min(labels.length-1,inspected+(e.key==='ArrowRight'?1:-1)));viewport.scrollLeft=Math.max(0,x(inspected)-viewport.clientWidth/2);inspect(viewport.querySelector('svg').getBoundingClientRect().left+x(inspected))});
  const hideTip=()=>{tip.hidden=true;viewport.querySelector('.trend-cursor').setAttribute('visibility','hidden')};
  viewport.addEventListener('pointermove',e=>inspect(e.clientX));viewport.addEventListener('click',e=>inspect(e.clientX));viewport.addEventListener('pointerleave',e=>{if(!tip.contains(e.relatedTarget))hideTip()});tip.addEventListener('pointerleave',hideTip);
  const note=document.createElement('p');note.className='trend-caption';note.textContent=caption+(continuous?'. Scroll horizontally to follow the next day.':'. Toggle legend labels to compare lines.');root.append(note);
 }
 function redraw(){if(latest)render(latest)}
 function render(data){
  latest=data;for(const node of observed)if(!node.isConnected){observer.unobserve(node);observed.delete(node)}const days=data.trend_dates||[],records=data.hourly_by_day||[];
  const known=new Set(days),calendar=[];
  if(days.length){const d=new Date(days[0]+'T00:00:00Z'),end=days.at(-1);while(d.toISOString().slice(0,10)<=end){calendar.push(d.toISOString().slice(0,10));d.setUTCDate(d.getUTCDate()+1)}}
  const root=document.getElementById('chart'),oldScroll=root.querySelector('.trend-viewport')?.scrollLeft||0;root.replaceChildren();
  pickMode(root,[['compare','Compare days'],['continuous','Continuous']],preferences.watch,mode=>{preferences.watch=mode;redraw()});
  const byHour=new Map(records.map(r=>[r.day+'|'+r.hour,r.hours]));
  if(preferences.watch==='compare')draw(root,{id:'watch',labels:hours().map(hour=>({hour,label:hour+':00'})),series:days.map(day=>({name:day,values:hours().map(hour=>byHour.get(day+'|'+hour)||0)})),caption:'Estimated watch hours by hour / one line per date'});
  else{const labels=ticks(calendar,true);draw(root,{id:'watch-continuous',labels,series:days.length?[{name:'Estimated watch hours',values:labels.map(t=>known.has(t.day)?byHour.get(t.day+'|'+t.hour)||0:null)}]:[],continuous:true,caption:'Estimated watch hours / consecutive dates; unloaded dates appear as gaps'})}
  const scroll=root.querySelector('.trend-viewport');if(scroll)scroll.scrollLeft=oldScroll;
  addExpand(root,'watch');
  for(const [index,field] of ['device_type','os','region','isp'].entries()){
   const panel=document.querySelector(`[data-layout-id="breakdown-${index}"] .breakdown`)||document.querySelectorAll('#breakdowns>.breakdown')[index];if(!panel)continue;if(!observed.has(panel)){observed.add(panel);observer.observe(panel)}
   const priorScroll=panel.querySelector('.breakdown-trend .trend-viewport')?.scrollLeft||0;panel.querySelector('.breakdown-trend')?.remove();const area=document.createElement('div');area.className='breakdown-trend';panel.querySelector('h3').after(area);
   const mode=preferences[field]||'daily';pickMode(area,[['totals','Totals'],['daily',days.length>1?'Daily trend':'Hourly trend'],['continuous','Hourly timeline']],mode,value=>{preferences[field]=value;redraw()});panel.classList.toggle('trend-show',mode!=='totals');addExpand(area,field);if(mode==='totals')continue;
   const continuous=mode==='continuous'||days.length===1,labels=continuous?ticks(calendar,true):ticks(calendar),rows=data.breakdown_trends?.[field]||[],points=new Map();
   for(const r of rows){const key=r.label+'|'+r.day+(continuous?'|'+r.hour:'');points.set(key,(points.get(key)||0)+r.hours)}
   const series=(data.breakdown[field]||[]).map(r=>({name:r.label,values:labels.map(t=>known.has(t.day)?points.get(r.label+'|'+t.day+(continuous?'|'+t.hour:''))||0:null)}));
   draw(area,{id:field,labels,series,continuous:mode==='continuous',caption:'Top 5 in the applied selection / estimated watch hours'+(continuous?' by hour':' by date')});const plot=area.querySelector('.trend-viewport');if(plot)plot.scrollLeft=priorScroll;
  }
  renderExpanded();
 }
 window.renderWatchTrends=render;
 const observer=new ResizeObserver(entries=>{let changed=false;for(const e of entries){if(widths.get(e.target)!==e.contentRect.width)changed=true;widths.set(e.target,e.contentRect.width)}if(changed){cancelAnimationFrame(frame);frame=requestAnimationFrame(redraw)}});
 observer.observe(document.getElementById('chart'));
 window.addEventListener('resize',()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(redraw)});
})();

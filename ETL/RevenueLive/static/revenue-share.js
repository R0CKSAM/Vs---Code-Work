'use strict';
window.RevenueShare=(()=>{
  let redrawTree=()=>{};
  window.addEventListener('resize',()=>requestAnimationFrame(()=>redrawTree()));
  const colors=['#f8cf96','#f990ad','#a8c7ec','#c9b1e5','#8dd4bf','#91b9cd'];
  const channelIcon=name=>/music|9xm|tashan|jhakaas|jalwa/i.test(name)?'music-2':/kids/i.test(name)?'smile':/bhojpuri|bollywood/i.test(name)?'clapperboard':'tv-minimal';
  const sparks=new Map();
  function sparkFill(context,color){
    const {ctx,chartArea}=context.chart;if(!chartArea)return color+'26';
    const fill=ctx.createLinearGradient(0,chartArea.top,0,chartArea.bottom);
    fill.addColorStop(0,color+'50');fill.addColorStop(1,color+'00');return fill;
  }
  const sparkKeys=[['total',['ad','other'],'#19a994'],['ad',['ad','other'],'#db668e'],['views',['views'],'#508ff0'],['impressions',['impressions'],'#d59636']];
  for(const [id] of sparkKeys){const frame=document.createElement('div'),canvas=document.createElement('canvas');frame.className='metric-spark';canvas.id='metricSpark-'+id;canvas.setAttribute('aria-hidden','true');frame.append(canvas);document.getElementById(id).closest('article').append(frame);}
  function renderSparks(rows){
    for(const chart of sparks.values())chart.destroy();sparks.clear();
    const grouped=new Map();for(const row of rows){if(!grouped.has(row.day))grouped.set(row.day,{ad:0,other:0,views:0,impressions:0});const day=grouped.get(row.day);for(const key of ['ad','other','views','impressions'])day[key]+=row[key];}
    const dates=[...grouped.keys()].sort(),labels=[];
    if(dates.length){const date=new Date(dates[0]+'T00:00:00Z');while(date.toISOString().slice(0,10)<=dates.at(-1)){labels.push(date.toISOString().slice(0,10));date.setUTCDate(date.getUTCDate()+1);}}
    for(const [id,keys,color] of sparkKeys){const canvas=document.getElementById('metricSpark-'+id);canvas.parentElement.hidden=dates.length<2;canvas.parentElement.title=dates.length>1?'Daily trend: '+dates[0]+' to '+dates.at(-1):'';if(dates.length<2)continue;
      const series=id==='ad'?keys.filter(key=>rows.some(row=>row[key]!==0)):[id];
      sparks.set(id,new Chart(canvas,{type:'line',data:{labels,datasets:series.map((key,index)=>({data:labels.map(day=>{const value=grouped.get(day);return value?key==='total'?value.ad+value.other:value[key]:null;}),borderColor:index?'#a45c85':color,backgroundColor:context=>sparkFill(context,index?'#a45c85':color),borderWidth:1.5,pointRadius:labels.length===1?3:0,fill:true,cubicInterpolationMode:'monotone',spanGaps:false}))},options:{responsive:true,maintainAspectRatio:false,animation:false,events:[],plugins:{legend:{display:false},tooltip:{enabled:false}},scales:{x:{display:false},y:{display:false,beginAtZero:true}},layout:{padding:3}}}));
    }
  }
  const cash=value=>new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:0,minimumFractionDigits:0}).format(value/100);
  const percent=(value,total)=>total>0?Math.round(value/total*100)+'%':'0%';
  const trigger=document.createElement('button');trigger.type='button';trigger.id='revenueShare';trigger.setAttribute('aria-expanded','false');trigger.setAttribute('aria-controls','revenueShareExpanded');trigger.setAttribute('aria-label','Revenue share: expand all channels');
  trigger.innerHTML='<span class="share-title">Revenue share <span aria-hidden="true">&#8599;</span></span><span class="share-content"><span class="share-ring"><canvas id="summaryShareCanvas" aria-hidden="true"></canvas><span class="share-centre"><strong id="shareSum"></strong><span>Total revenue</span></span></span><span id="summaryShareLegend"></span></span><span id="shareMessage"></span>';
  document.querySelector('#dashboard .metrics').after(trigger);
  const modal=document.createElement('section');modal.id='revenueShareExpanded';modal.hidden=true;modal.setAttribute('aria-labelledby','revenueShareTitle');modal.innerHTML='<div class="share-dialog-heading"><h2 id="revenueShareTitle">Revenue by channel</h2><button type="button" aria-label="Collapse channel distribution" title="Collapse">&#8722;</button></div><div id="fullShareRows"></div>';
  trigger.after(modal);
  const overview=document.createElement('div');overview.id='revenueOverview';trigger.before(overview);overview.append(trigger,modal);
  const trend=document.createElement('section');trend.className='daily-revenue';trend.innerHTML='<h2>Revenue over time</h2><div class="daily-revenue-canvas"><canvas id="dailyRevenueCanvas" role="img" aria-label="Daily ad and sponsorship revenue"></canvas></div><p id="dailyRevenueNote"></p>';overview.append(trend);
  const views=document.createElement('section');views.id='viewsDistribution';views.innerHTML='<h2>Views distribution</h2><div id="viewsDistributionRows"></div><p id="viewsDistributionEmpty"></p>';overview.after(views);
  const metrics=document.createElement('section');metrics.id='channelMetrics';metrics.innerHTML='<h2>Channel metrics</h2><div class="metrics-table-scroll"><table><thead><tr><th scope="col">Channel</th><th scope="col">Views</th><th scope="col">Ad impressions</th><th scope="col">Ad revenue</th><th scope="col">Sponsorship / others</th><th scope="col">Total revenue</th></tr></thead><tbody></tbody></table></div><p class="metrics-empty"></p>';views.before(metrics);
  const metricsToggle=document.createElement('button');metricsToggle.type='button';metricsToggle.className='metrics-toggle';metricsToggle.setAttribute('aria-expanded','false');metricsToggle.setAttribute('aria-controls','channelMetricsBody');metricsToggle.title='Expand channel metrics';metricsToggle.innerHTML='<span>Channel metrics</span><i data-lucide="maximize-2" aria-hidden="true"></i>';metrics.querySelector('h2').replaceWith(metricsToggle);metrics.querySelector('tbody').id='channelMetricsBody';let metricsExpanded=false;
  function sizeMetrics(){metrics.querySelectorAll('tbody tr').forEach((row,i)=>row.hidden=!metricsExpanded&&i>=5);metricsToggle.setAttribute('aria-expanded',String(metricsExpanded));const action=metricsExpanded?'Collapse':'Expand';metricsToggle.title=action+' channel metrics';metricsToggle.setAttribute('aria-label',action+' channel metrics');metricsToggle.querySelector('span').textContent='Channel metrics';const oldIcon=metricsToggle.querySelector('svg,i');const nextIcon=document.createElement('i');nextIcon.dataset.lucide=metricsExpanded?'minimize-2':'maximize-2';nextIcon.setAttribute('aria-hidden','true');oldIcon.replaceWith(nextIcon);window.lucide?.createIcons();}
  metricsToggle.addEventListener('click',()=>{metricsExpanded=!metricsExpanded;sizeMetrics();});
  const treeButton=document.createElement('button');treeButton.type='button';treeButton.id='viewsTreeButton';treeButton.setAttribute('aria-expanded','false');treeButton.setAttribute('aria-controls','viewsDistributionRows');treeButton.innerHTML='<span class="share-title">Views distribution <span aria-hidden="true">&#8599;</span></span><span id="viewsTree"></span>';
  views.prepend(treeButton);views.querySelector('h2').hidden=true;document.getElementById('viewsDistributionRows').hidden=true;
  const treeLegend=document.createElement('span');treeLegend.id='viewsTreeLegend';treeButton.append(treeLegend);
  const collapseViews=document.createElement('button');collapseViews.type='button';collapseViews.textContent='Collapse';collapseViews.hidden=true;treeButton.after(collapseViews);
  function closeViews(){treeButton.hidden=false;collapseViews.hidden=true;views.querySelector('h2').hidden=true;document.getElementById('viewsDistributionRows').hidden=true;treeButton.setAttribute('aria-expanded','false');redrawTree();}
  treeButton.addEventListener('click',()=>{treeButton.hidden=true;collapseViews.hidden=false;views.querySelector('h2').hidden=false;document.getElementById('viewsDistributionRows').hidden=false;treeButton.setAttribute('aria-expanded','true');collapseViews.focus({preventScroll:true});});
  collapseViews.addEventListener('click',()=>{closeViews();treeButton.focus();});
  for(const button of [collapseViews,modal.querySelector('button')]){button.classList.add('distribution-collapse');button.setAttribute('aria-label','Collapse distribution');button.title='Collapse distribution';button.innerHTML='<i data-lucide="minimize-2" aria-hidden="true"></i>';}
  for(const button of [trigger,treeButton]){const arrow=button.querySelector('.share-title>span');arrow.innerHTML='<i data-lucide="maximize-2" aria-hidden="true"></i>';button.title='Expand distribution';}
  window.lucide?.createIcons();
  document.addEventListener('keydown',event=>{if(event.key!=='Escape')return;if(!modal.hidden){collapse();trigger.focus();}else if(!collapseViews.hidden){closeViews();treeButton.focus();}});
  let lineChart=null;
  let chart=null,entries=[],total=0;
  function collapse(){modal.hidden=true;trigger.hidden=false;trigger.setAttribute('aria-expanded','false');}
  modal.querySelector('button').addEventListener('click',()=>{collapse();trigger.focus();});
  trigger.addEventListener('click',()=>{modal.hidden=false;trigger.hidden=true;trigger.setAttribute('aria-expanded','true');modal.querySelector('button').focus({preventScroll:true});});
  function row(name,value,index,full=false){
    const el=document.createElement('span');el.className=full?'full-share-row':'compact-share-row';
    const label=document.createElement('span');label.className='share-channel';label.textContent=name;label.title=name;
    const values=document.createElement('strong');values.textContent=cash(value)+' | '+percent(value,total);
    el.style.setProperty('--share-color',colors[index%colors.length]);el.append(label,values);
    if(full){const track=document.createElement('span');track.className='distribution-track';const fill=document.createElement('span');fill.style.width=(total>0?Math.max(0,value)/total*100:0)+'%';track.append(fill);el.append(track);}
    return el;
  }
  function render(rows){
    renderSparks(rows);
    const metricSums=new Map();for(const r of rows){if(!metricSums.has(r.channel))metricSums.set(r.channel,{views:0,impressions:0,ad:0,other:0,total:0});for(const key of ['views','impressions','ad','other','total'])metricSums.get(r.channel)[key]+=r[key];}
    const keys=['views','impressions','ad','other','total'];
    // Independent column scales use unrounded values and all selected channels.
    const scales=keys.map(key=>{const values=[...metricSums.values()].map(value=>value[key]).sort((a,b)=>a-b),length=values.length;return {minimum:values[0]??0,maximum:values.at(-1)??0,middle:length?(length%2?values[Math.floor(length/2)]:(values[length/2-1]+values[length/2])/2):0};});
    function heatColor(n,{minimum,maximum,middle}){let low,high,f;if(minimum===maximum){low=high=n===0?[248,105,107]:[255,235,132];f=0;}else if(n<=minimum){low=high=[248,105,107];f=0;}else if(n>=maximum){low=high=[99,190,123];f=0;}else if(n<=middle&&middle>minimum){low=[248,105,107];high=[255,235,132];f=(n-minimum)/(middle-minimum);}else{low=[255,235,132];high=[99,190,123];f=(n-middle)/(maximum-middle);}return 'rgb('+low.map((value,i)=>(value+(high[i]-value)*f).toFixed(3)).join(',')+')';}
    metrics.querySelector('tbody').replaceChildren(...[...metricSums].sort((a,b)=>b[1].total-a[1].total||a[0].localeCompare(b[0])).map(([name,values])=>{const tr=document.createElement('tr'),label=document.createElement('th');label.scope='row';label.textContent=name;tr.append(label);keys.forEach((key,i)=>{const cell=document.createElement('td'),n=values[key];cell.dataset.label=['Views','Ad impressions','Ad revenue','Sponsorship / others','Total revenue'][i];cell.textContent=i<2?new Intl.NumberFormat('en-IN').format(n):cash(n);cell.style.backgroundColor=heatColor(n,scales[i]);cell.style.color='#202a30';cell.title=cell.dataset.label+': independent column scale; minimum red, median yellow, maximum green. Equal nonzero values yellow; all-zero values red.';tr.append(cell);});return tr;}));
    for(const [index,label] of [...metrics.querySelectorAll('tbody th')].entries()){const name=document.createElement('span'),badge=document.createElement('span'),glyph=document.createElement('i');name.textContent=label.textContent;badge.className='channel-glyph';badge.style.backgroundColor=colors[index%colors.length]+'55';glyph.dataset.lucide=channelIcon(name.textContent);glyph.setAttribute('aria-hidden','true');badge.append(glyph);label.replaceChildren(badge,name);}
    window.lucide?.createIcons();sizeMetrics();
    metrics.querySelector('.metrics-empty').textContent=rows.length?'':'No channel data for this selection.';
    const days=new Map(),viewSums=new Map();
    for(const r of rows){if(!days.has(r.day))days.set(r.day,{ad:0,other:0});days.get(r.day).ad+=r.ad;days.get(r.day).other+=r.other;viewSums.set(r.channel,(viewSums.get(r.channel)||0)+r.views);}
    const sorted=[...days].sort(([a],[b])=>a.localeCompare(b));
    const datasets=[['Ad revenue','ad','#09aaa1'],['Sponsorship / others','other','#fa668c']].filter(([,key])=>sorted.some(([,v])=>v[key]!==0)).map(([label,key,color])=>({label,data:sorted.map(([,v])=>v[key]/100),borderColor:color,backgroundColor:color+'12',borderWidth:2,fill:true,tension:0,pointRadius:sorted.length===1?5:3,pointHoverRadius:5}));
    const first=document.getElementById('start').value||sorted[0]?.[0],last=document.getElementById('end').value||sorted.at(-1)?.[0];
    const span=first&&last?(Date.parse(last)-Date.parse(first))/86400000+1:0;
    const useBars=sorted.length===1||(span>0&&span<=7);
    if(useBars)for(const dataset of datasets){dataset.type='bar';dataset.backgroundColor=dataset.borderColor;dataset.borderWidth=0;dataset.borderRadius=3;dataset.maxBarThickness=48;dataset.categoryPercentage=.7;dataset.barPercentage=.85;}
    if(lineChart)lineChart.destroy();
    Chart.defaults.color='#514958';Chart.defaults.font.size=13;
    lineChart=new Chart(document.getElementById('dailyRevenueCanvas'),{type:useBars?'bar':'line',data:{labels:sorted.map(([day])=>day),datasets},options:{responsive:true,maintainAspectRatio:false,animation:matchMedia('(prefers-reduced-motion: reduce)').matches?false:{duration:250},interaction:{mode:'index',intersect:false},plugins:{legend:{position:'bottom',labels:{color:'#d1d1dc',boxWidth:12}},tooltip:{callbacks:{label:ctx=>ctx.dataset.label+': '+cash(ctx.raw*100)}}},scales:{x:{type:'category',offset:useBars,title:{display:true,text:'Date',color:'#bcbccc'},grid:{display:false,offset:useBars},ticks:{color:'#bcbccc',maxTicksLimit:6,maxRotation:0,callback:function(value){const day=this.getLabelForValue(value);return new Intl.DateTimeFormat('en-GB',{day:'2-digit',month:'short',timeZone:'UTC'}).format(new Date(day+'T00:00:00Z'));}}},y:{beginAtZero:true,title:{display:true,text:'Revenue (INR)',color:'#bcbccc'},grid:{color:'#ffffff0d'},ticks:{color:'#bcbccc'}}}}});
    lineChart.stop();for(const axis of Object.values(lineChart.options.scales)){axis.ticks.color='#506889';axis.title.color='#506889';axis.grid.color='#edf2f8';}lineChart.options.plugins.legend.labels.color='#506889';lineChart.options.plugins.legend.labels.usePointStyle=true;lineChart.options.plugins.legend.labels.pointStyle='circle';lineChart.options.plugins.legend.labels.padding=20;lineChart.update('none');
    document.getElementById('dailyRevenueNote').textContent=!rows.length?'No data in this selection.':!datasets.length?'No revenue in this selection.':sorted.length===1?'One date available. Select a wider range to compare days.':'';
    document.getElementById('dailyRevenueCanvas').setAttribute('aria-label',useBars?'Daily ad and sponsorship revenue grouped bars':'Daily ad and sponsorship revenue lines');
    const viewEntries=[...viewSums].sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0])),viewTotal=viewEntries.reduce((sum,[,n])=>sum+n,0);
    const tree=document.getElementById('viewsTree');tree.replaceChildren();
    const positive=viewEntries;
    treeButton.title='Expand views distribution';
    treeLegend.replaceChildren(...viewEntries.map(([name,n],index)=>{const item=document.createElement('span');item.className='tree-legend-item';item.style.setProperty('--share-color',colors[index%colors.length]);const label=document.createElement('span');label.textContent=(index+1)+'. '+name;const value=document.createElement('strong');value.textContent=new Intl.NumberFormat('en-IN').format(n)+' views | '+percent(n,viewTotal);item.append(label,value);return item;}));
    // Equal-sized tiles keep every channel readable; percentages convey its actual share.
    function tile(items,x,y,w,h){
      if(!items.length)return;
      if(items.length===1){const [name,n]=items[0],el=document.createElement('span'),index=positive.indexOf(items[0]);el.className='views-tree-tile';el.style.cssText=`left:${x}%;top:${y}%;width:${w}%;height:${h}%;background:${colors[index%colors.length]}`;el.title=name+' | '+new Intl.NumberFormat('en-IN').format(n)+' views | '+percent(n,viewTotal);el.setAttribute('aria-label',el.title);const label=document.createElement('span');label.textContent=(index+1)+'. '+name;const value=document.createElement('strong');value.textContent=new Intl.NumberFormat('en-IN').format(n)+' views';const badge=document.createElement('span'),glyph=document.createElement('i');badge.className='tile-channel-icon';glyph.dataset.lucide=channelIcon(name);glyph.setAttribute('aria-hidden','true');badge.append(glyph);const share=document.createElement('small');share.className='tile-share';share.textContent=percent(n,viewTotal)+' share';value.append(share);el.append(label,badge,value);tree.append(el);return;}
    }
    redrawTree=()=>{
      if(!tree.clientWidth)return;
      tree.style.height='auto';tree.replaceChildren();
      for(const item of positive)tile([item],0,0,100,100);
      for(const [index,element] of [...tree.children].entries())element.style.setProperty('--channel-accent',colors[index%colors.length]);
      window.lucide?.createIcons();
    };
    redrawTree();treeButton.disabled=!positive.length;
    document.getElementById('viewsDistributionRows').replaceChildren(...viewEntries.map(([name,n],i)=>{const el=document.createElement('div');el.className='full-share-row';el.style.setProperty('--share-color',colors[i%colors.length]);const label=document.createElement('span');label.className='share-channel';label.textContent=name;const value=document.createElement('strong');value.textContent=new Intl.NumberFormat('en-IN').format(n)+' views | '+percent(n,viewTotal);const track=document.createElement('span');track.className='distribution-track';const fill=document.createElement('span');fill.style.width=(viewTotal>0?n/viewTotal*100:0)+'%';track.append(fill);el.append(label,value,track);return el;}));
    document.getElementById('viewsDistributionEmpty').textContent=!viewEntries.length?'No views data in this selection.':viewTotal===0?'No views recorded.':'';
    const sums=new Map();for(const r of rows)sums.set(r.channel,(sums.get(r.channel)||0)+r.total);
    entries=[...sums].sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0]));total=entries.reduce((sum,[,value])=>sum+value,0);
    trigger.classList.toggle('few-channels',entries.length<=2);
    document.getElementById('fullShareRows').classList.toggle('many-channels',entries.length>8);
    document.getElementById('viewsDistributionRows').classList.toggle('many-channels',viewEntries.length>8);
    const valid=total>0&&entries.every(([,value])=>value>=0);
    const shown=entries.slice(0,5);if(entries.length>5)shown.push(['Others ('+(entries.length-5)+')',entries.slice(5).reduce((sum,[,value])=>sum+value,0)]);
    document.getElementById('shareSum').textContent=cash(total);
    const sumLabel=document.getElementById('shareSum');sumLabel.title=cash(total);sumLabel.style.fontSize='14px';
    requestAnimationFrame(()=>{let size=14;while(sumLabel.scrollWidth>sumLabel.clientWidth&&size>8){size-=.5;sumLabel.style.fontSize=size+'px';}});
    document.getElementById('summaryShareLegend').replaceChildren(...shown.map(([name,value],i)=>row(name,value,i)));
    document.getElementById('fullShareRows').replaceChildren(...entries.map(([name,value],i)=>row(name,value,i,true)));
    document.getElementById('shareMessage').textContent=!rows.length?'No revenue data in this selection.':!valid?'Share chart unavailable for zero or negative revenue.':'';
    trigger.disabled=!entries.length;
    if(chart)chart.destroy();
    chart=new Chart(document.getElementById('summaryShareCanvas'),{type:'doughnut',data:{labels:shown.map(([name])=>name),datasets:[{data:valid?shown.map(([,value])=>value):[],backgroundColor:colors,borderWidth:1,borderColor:'#fff',hoverOffset:0}]},options:{responsive:true,maintainAspectRatio:false,cutout:'66%',events:[],animation:false,plugins:{visibleSharePercent:false,legend:{display:false},tooltip:{enabled:false}}}});
    modal.querySelectorAll('.distribution-track').forEach(el=>el.hidden=!valid);
  }
  function clear(){collapse();closeViews();render([]);}
  return{render,clear};
})();

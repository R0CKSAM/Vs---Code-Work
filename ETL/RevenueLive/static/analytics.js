'use strict';
// All charts consume the same already-authorized, applied report rows.
window.RevenueCharts=(()=>{
  const palette=['#087f68','#328db5','#bd7e16','#9258a9','#d36c70','#568148','#5368ba','#627b89'];
  const charts={};let rows=[],expanded=null;
  const extra=document.createElement('div');extra.id='channelAnalysis';extra.className='channel-analysis';
  extra.innerHTML='<section class="chart-block"><div class="chart-heading"><h3>Views and revenue</h3><button data-expand="combinedChart" type="button">Expand</button></div><div class="chart-frame"><canvas id="combinedChart" role="img" aria-label="Views and revenue trend"></canvas></div></section><section class="chart-block"><div class="chart-heading"><h3>Channel comparison</h3><button data-expand="radarChart" type="button">Expand</button></div><div class="chart-frame"><canvas id="radarChart" role="img" aria-label="Normalized channel comparison"></canvas></div><small>Top six by revenue. Each metric normalized to the selected-channel maximum.</small></section><section class="chart-block"><h3>Views distribution</h3><div id="viewsTreemap" class="views-treemap"></div></section><section class="chart-block heatmap-block"><h3>Channel metrics</h3><small>RPM: revenue per 1,000 views. Shading compares values within each column.</small><div class="heatmap-scroll"><table><thead><tr><th>Channel</th><th>Views</th><th>Ad impressions</th><th>Ad revenue</th><th>Total revenue</th><th>RPM</th></tr></thead><tbody id="metricHeatmap"></tbody></table></div></section>';
  extra.querySelector('#radarChart').closest('.chart-block').remove();
  const relationship=document.createElement('section');relationship.className='chart-block revenue-composition';
  relationship.innerHTML='<div class="chart-heading"><h3>Revenue composition</h3><button type="button" data-expand="compositionChart">Expand</button></div><div class="composition-ring"><div class="chart-frame"><canvas id="compositionChart" role="img" aria-label="Ad revenue and sponsorship share"></canvas></div><div class="composition-total"><span>Total revenue</span><strong id="compositionTotal"></strong></div></div><div id="compositionLegend" class="composition-legend"></div>';
  const audience=document.createElement('section');audience.className='chart-block';audience.innerHTML='<div class="chart-heading"><h3>Audience activity</h3><button type="button" data-expand="audienceChart">Expand</button></div><div class="chart-frame"><canvas id="audienceChart" role="img" aria-label="Views and ad impressions over time"></canvas></div>';
  extra.firstElementChild.after(relationship,audience);
  const legacyGrid=document.getElementById('chartGrid');
  const additional=document.createElement('details');additional.id='additionalCharts';
  const summary=document.createElement('summary');summary.textContent='Additional charts';additional.append(summary);
  legacyGrid.before(extra,additional);additional.append(legacyGrid);
  additional.addEventListener('toggle',()=>{if(additional.open)requestAnimationFrame(()=>Object.values(charts).forEach(chart=>{if(legacyGrid.contains(chart.canvas))chart.resize();}));});
  function additionalCharts(a,labels){
    const totals=a.channels.reduce((sum,[,v])=>({ad:sum.ad+v.ad,other:sum.other+v.other,total:sum.total+v.total}),{ad:0,other:0,total:0});
    const valid=totals.ad>=0&&totals.other>=0&&totals.total>0;
    document.getElementById('compositionTotal').textContent=rupee(totals.total/100);
    document.getElementById('compositionLegend').replaceChildren(...[['Ad revenue',totals.ad,'#42d6ad'],['Sponsorship / others',totals.other,'#f2b764']].map(([label,value,color])=>{const item=document.createElement('div');item.style.borderLeft='3px solid '+color;const name=document.createElement('span'),amount=document.createElement('strong');name.textContent=label;amount.textContent=rupee(value/100)+(valid?' | '+(value/totals.total*100).toFixed(1)+'%':'');item.append(name,amount);return item;}));
    draw('compositionChart','doughnut',{labels:['Ad revenue','Sponsorship / others'],datasets:[{data:valid?[totals.ad/100,totals.other/100]:[],backgroundColor:['#42d6ad','#f2b764'],borderWidth:0,hoverOffset:4}]},{responsive:true,maintainAspectRatio:false,cutout:'78%',plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>c.label+': '+rupee(c.raw)}}}});
    const audienceOptions=base();audienceOptions.plugins.legend.display=true;audienceOptions.plugins.legend.position='bottom';
    draw('audienceChart','line',{labels,datasets:[['Views','views','#66c8f0'],['Ad impressions','impressions','#f2b764']].map(([label,key,color])=>({label,data:a.dates.map(([,v])=>v[key]),borderColor:color,backgroundColor:color+'16',fill:true,borderWidth:2,pointRadius:labels.length===1?5:2,tension:.15}))},audienceOptions);
    let opts=base();opts.plugins.legend.display=true;opts.plugins.legend.position='bottom';opts.scales.y.title={display:true,text:'Views'};opts.scales.revenue={position:'right',beginAtZero:true,grid:{drawOnChartArea:false},title:{display:true,text:'Revenue (INR)'},ticks:{callback:short}};
    opts.plugins.tooltip={callbacks:{label:c=>c.dataset.label+': '+(c.dataset.yAxisID==='revenue'?rupee(c.raw):fmt(c.raw))}};
    draw('combinedChart','bar',{labels,datasets:[{type:'line',label:'Views',data:a.dates.map(([,v])=>v.views),borderColor:'#328db5',pointRadius:2,yAxisID:'y',order:0},{label:'Revenue',data:a.dates.map(([,v])=>v.total/100),backgroundColor:'#a9bdde',yAxisID:'revenue',order:1}]},opts);
    const metrics=a.channels.map(([name,v])=>({name,values:[v.views,v.impressions,v.ad/100,v.total/100,v.views?v.total/100/v.views*1000:null]}));
    const maxima=Array.from({length:5},(_,i)=>Math.max(0,...metrics.map(v=>v.values[i]||0)));
    const heat=document.getElementById('metricHeatmap');heat.replaceChildren();
    for(const v of metrics){const tr=document.createElement('tr'),name=document.createElement('td');name.textContent=v.name;tr.append(name);v.values.forEach((n,i)=>{const td=document.createElement('td');td.className='heat-'+(n===null||!maxima[i]?0:Math.min(4,Math.floor(n/maxima[i]*4)));td.textContent=n===null?'N/A':i>=2?rupee(n):fmt(n);tr.append(td);});heat.append(tr);}
    const tree=document.getElementById('viewsTreemap');tree.replaceChildren();
    const values=[...a.channels].filter(([,v])=>v.views>0).sort((a,b)=>b[1].views-a[1].views);
    const total=values.reduce((n,[,v])=>n+v.views,0);
    function tile(items,x,y,w,h){
      if(!items.length)return;
      if(items.length===1){const [name,v]=items[0],el=document.createElement('div');el.className='tree-tile';el.style.left=x+'%';el.style.top=y+'%';el.style.width=w+'%';el.style.height=h+'%';el.style.background=palette[values.indexOf(items[0])%palette.length];el.tabIndex=0;el.title=name+': '+fmt(v.views)+' views ('+(v.views/total*100).toFixed(1)+'%)';el.setAttribute('aria-label',el.title);const label=document.createElement('strong'),amount=document.createElement('span');label.textContent=name;amount.textContent=short(v.views)+' | '+(v.views/total*100).toFixed(1)+'%';el.append(label,amount);tree.append(el);return;}
      const sum=items.reduce((n,[,v])=>n+v.views,0);let subtotal=0,k=0;while(k<items.length-1&&subtotal<sum/2)subtotal+=items[k++][1].views;const f=subtotal/sum;
      if(w*tree.clientWidth>=h*tree.clientHeight){tile(items.slice(0,k),x,y,w*f,h);tile(items.slice(k),x+w*f,y,w*(1-f),h);}else{tile(items.slice(0,k),x,y,w,h*f);tile(items.slice(k),x,y+h*f,w,h*(1-f));}
    }
    if(total)tile(values,0,0,100,100);else tree.textContent='No views in this selection.';
  }
  Chart.register({id:'visibleSharePercent',afterDatasetsDraw(chart){
    if(chart.config.type!=='doughnut')return;
    const values=chart.data.datasets[0].data,total=values.reduce((sum,v)=>sum+v,0);if(!total)return;
    const ctx=chart.ctx;ctx.save();ctx.font='bold 12px Arial';ctx.textAlign='center';ctx.textBaseline='middle';
    chart.getDatasetMeta(0).data.forEach((arc,i)=>{const percent=values[i]/total*100;if(percent<7||arc.outerRadius-arc.innerRadius<22)return;const point=arc.tooltipPosition();const label=percent.toFixed(1)+'%';ctx.lineWidth=3;ctx.strokeStyle='#17352d';ctx.strokeText(label,point.x,point.y);ctx.fillStyle='#fff';ctx.fillText(label,point.x,point.y);});ctx.restore();
  }});
  const fmt=n=>new Intl.NumberFormat('en-IN').format(n);
  const rupee=n=>new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:2}).format(n);
  const short=n=>new Intl.NumberFormat('en-IN',{notation:'compact',maximumFractionDigits:1}).format(n);
  function shareDetails(id,channels,key){
    const ranked=[...channels].sort((a,b)=>b[1][key]-a[1][key]),sum=ranked.reduce((n,[,v])=>n+v[key],0);
    let count=ranked.length;
    if(count>7){count=0;let subtotal=0;while(count<6&&subtotal<sum*.6){subtotal+=ranked[count][1][key];count++;}count=Math.max(1,count);}
    const items=ranked.slice(0,count).map(([name,v])=>({name,value:v[key]}));
    if(count<ranked.length)items.push({name:'Others ('+(ranked.length-count)+' channels)',value:ranked.slice(count).reduce((n,[,v])=>n+v[key],0)});
    const canvas=document.getElementById(id),block=canvas.closest('.chart-block');block.classList.add('share-block');
    let list=block.querySelector('.share-values');if(!list){list=document.createElement('div');list.className='share-values';canvas.parentElement.after(list);}
    list.replaceChildren();
    for(const [i,item] of items.entries()){const row=document.createElement('div'),label=document.createElement('span'),value=document.createElement('strong');row.className='share-item share-color-'+i;label.textContent=item.name;label.title=item.name;value.textContent=(key==='total'?rupee(item.value/100):fmt(item.value))+' | '+(sum?(item.value/sum*100).toFixed(1)+'%':'N/A');row.append(label,value);list.append(row);}
    return {items,sum};
  }
  const emptyPlugin={id:'zeroNotice',afterDraw(chart){if(['doughnut','pie'].includes(chart.config.type)&&chart.data.datasets[0].data.every(v=>v===0)){const{ctx,chartArea:a}=chart;ctx.save();ctx.fillStyle='#65737b';ctx.font='14px Arial';ctx.textAlign='center';ctx.fillText('No revenue in this selection',(a.left+a.right)/2,(a.top+a.bottom)/2);ctx.restore();}}};
  function bucket(day,interval){const date=new Date(day+'T00:00:00Z');if(interval==='month')return day.slice(0,7);if(interval==='week'){date.setUTCDate(date.getUTCDate()-(date.getUTCDay()+6)%7);return date.toISOString().slice(0,10);}return day;}
  function aggregate(values,interval='day'){
    const channels=new Map(),dates=new Map();
    for(const row of values){
      const key=bucket(row.day,interval);
      if(!dates.has(key))dates.set(key,{total:0,ad:0,other:0,views:0,impressions:0});
      if(!channels.has(row.channel))channels.set(row.channel,{total:0,ad:0,other:0,views:0,impressions:0});
      for(const target of [dates.get(key),channels.get(row.channel)])for(const k of ['total','ad','other','views','impressions'])target[k]+=row[k];
    }
    return{channels:[...channels].sort((a,b)=>b[1].total-a[1].total||a[0].localeCompare(b[0])),dates:[...dates].sort((a,b)=>a[0].localeCompare(b[0]))};
  }
  function base(){return{
    responsive:true,maintainAspectRatio:false,animation:false,
    interaction:{mode:'index',intersect:false},
    plugins:{legend:{display:false,labels:{boxWidth:10,font:{size:11},color:'#53656c'}}},
    scales:{
      x:{display:true,border:{display:true,color:'#80939d'},grid:{display:false},title:{display:true,text:'Date',color:'#364b55',font:{size:12},padding:6},ticks:{color:'#364b55',font:{size:12},padding:8,maxRotation:0,minRotation:0,autoSkip:true,maxTicksLimit:5,callback:function(value){const label=String(this.getLabelForValue(value));const raw=label.replace('Week of ','');if(/^\d{4}-\d{2}(-\d{2})?$/.test(raw)){const date=new Date(raw+(raw.length===7?'-01':'')+'T00:00:00Z');return new Intl.DateTimeFormat('en-GB',{day:raw.length===7?undefined:'2-digit',month:'short',year:raw.length===7?'numeric':undefined,timeZone:'UTC'}).format(date);}return label;}}},
      y:{beginAtZero:true,border:{display:false},grid:{color:'#e1e7e9'},ticks:{color:'#65737b',callback:short}}
    }
  };}
  function draw(id,type,data,options){
    const canvas=document.getElementById(id);
    options.animation=matchMedia('(prefers-reduced-motion: reduce)').matches?false:{duration:350};
    for(const axis of Object.values(options.scales||{})){if(axis.ticks)axis.ticks.color='#b7c2c9';if(axis.title)axis.title.color='#b7c2c9';if(axis.grid&&axis.grid.display!==false)axis.grid.color='#ffffff12';}
    if(options.plugins?.legend)options.plugins.legend.labels={...options.plugins.legend.labels,color:'#b7c2c9'};
    if(type==='line'){
      let note=canvas.closest('.chart-block').querySelector('.single-point-note');
      if(!note){note=document.createElement('p');note.className='single-point-note chart-note';canvas.parentElement.after(note);}
      const single=data.labels.length===1;note.hidden=!single;
      note.textContent=single?'Only one time bucket has data ('+data.labels[0]+'). Select a wider range for a trend.':'';
      if(single){options.scales.x.offset=true;for(const dataset of data.datasets){dataset.pointRadius=6;dataset.pointHoverRadius=8;dataset.pointBackgroundColor=dataset.borderColor;}}
    }
    if(type==='doughnut')options.plugins.legend.display=false;
    if(charts[id])charts[id].destroy();charts[id]=new Chart(canvas,{type,data,options,plugins:[emptyPlugin]});
  }
  function render(values=rows){
    rows=values;const interval=document.getElementById('interval').value,metric=document.getElementById('trendMetric').value;
    const a=aggregate(rows,interval),monetary=['total','ad'].includes(metric),divisor=monetary?100:1;
    document.getElementById('chartsEmpty').hidden=rows.length>0;document.getElementById('chartGrid').hidden=rows.length===0;
    extra.hidden=rows.length===0;additional.hidden=rows.length===0;document.getElementById('metricHeatmap').replaceChildren();document.getElementById('viewsTreemap').replaceChildren();
    if(!rows.length){Object.values(charts).forEach(c=>c.destroy());for(const k in charts)delete charts[k];return;}
    const labels=a.dates.map(([d])=>interval==='week'?'Week of '+d:d);
    additionalCharts(a,labels);
    let options=base();options.scales.y.title={display:true,text:monetary?'INR':metric==='views'?'Views':'Ad impressions'};options.plugins.tooltip={callbacks:{label:c=>(monetary?rupee:fmt)(c.parsed.y)}};
    draw('trendChart','line',{labels,datasets:[{label:metric,data:a.dates.map(([,v])=>v[metric]/divisor),borderColor:palette[0],backgroundColor:'#087f6812',fill:true,tension:.15,pointRadius:labels.length>40?0:3,pointHoverRadius:6,borderWidth:2}]},options);
    for(const [id,key,color] of [['adTrend','ad',palette[1]],['viewsTrend','views',palette[3]],['otherTrend','other',palette[2]]]){
      const cash=key!=='views',opts=base();opts.plugins.tooltip={callbacks:{label:c=>(cash?rupee:fmt)(c.parsed.y)}};
      draw(id,'line',{labels,datasets:[{label:key,data:a.dates.map(([,v])=>v[key]/(cash?100:1)),borderColor:color,backgroundColor:color+'12',fill:true,tension:.15,pointRadius:labels.length>40?0:2,borderWidth:2}]},opts);
    }
    const revenueShare=shareDetails('shareChart',a.channels,'total');
    const top=revenueShare.items.map(item=>[item.name,{total:item.value}]);
    const revenue=top.map(([,r])=>r.total/100),total=revenue.reduce((n,v)=>n+v,0);
    options={responsive:true,maintainAspectRatio:false,animation:false,cutout:'65%',plugins:{
      legend:{position:'right',labels:{boxWidth:10,font:{size:11},generateLabels:chart=>chart.data.labels.map((text,i)=>({text:(text.length>20?text.slice(0,19)+'...':text)+' '+(total?(revenue[i]/total*100).toFixed(1)+'%':'N/A'),fillStyle:chart.data.datasets[0].backgroundColor[i],strokeStyle:'transparent',index:i}))}},
      tooltip:{callbacks:{label:c=>`${c.label}: ${rupee(c.raw)} (${total?(c.raw/total*100).toFixed(1):'0.0'}%)`}}
    }};
    options.plugins.legend.onClick=()=>{};
    draw('shareChart','doughnut',{labels:top.map(([name])=>name),datasets:[{data:revenue,backgroundColor:palette,borderWidth:2,borderColor:'#ffffff'}]},options);
    document.getElementById('shareNote').textContent='';
    const viewShare=shareDetails('viewsShare',a.channels,'views');
    const viewCanvas=document.getElementById('viewsShare'),viewBlock=viewCanvas.closest('.chart-block');
    viewCanvas.parentElement.hidden=a.channels.length===1;viewBlock.querySelector('[data-expand]').hidden=a.channels.length===1;
    if(a.channels.length!==1){draw('viewsShare','doughnut',{labels:viewShare.items.map(v=>v.name),datasets:[{data:viewShare.items.map(v=>v.value),backgroundColor:palette,borderWidth:2,borderColor:'#fff'}]},{responsive:true,maintainAspectRatio:false,animation:false,cutout:'65%',plugins:{legend:{position:'right',onClick:()=>{},labels:{boxWidth:10,generateLabels:chart=>viewShare.items.map((v,i)=>({text:(v.name.length>20?v.name.slice(0,19)+'...':v.name)+' '+(viewShare.sum?(v.value/viewShare.sum*100).toFixed(1)+'%':'N/A'),fillStyle:palette[i],index:i}))}},tooltip:{callbacks:{label:c=>fmt(c.raw)+' views | '+(viewShare.sum?(c.raw/viewShare.sum*100).toFixed(1)+'%':'N/A')}}}});}
    else if(charts.viewsShare){charts.viewsShare.destroy();delete charts.viewsShare;}
    const shareCanvas=document.getElementById('shareChart'),shareBlock=shareCanvas.closest('.chart-block');
    let single=document.getElementById('singleChannelRevenue');
    if(!single){single=document.createElement('div');single.id='singleChannelRevenue';shareCanvas.parentElement.after(single);}
    const one=a.channels.length===1;
    shareCanvas.parentElement.hidden=one;shareBlock.querySelector('[data-expand]').hidden=one;single.hidden=!one;
    single.replaceChildren();single.hidden=true;if(one){document.getElementById('shareNote').textContent='';charts.shareChart.destroy();delete charts.shareChart;}
    const limit=document.getElementById('rankLimit').value,ranked=limit==='all'?a.channels:a.channels.slice(0,Number(limit));
    document.getElementById('rankFrame').style.height=Math.max(290,ranked.length*31)+'px';
    options=base();options.indexAxis='y';options.scales.x={beginAtZero:true,grid:{color:'#e1e7e9'},title:{display:true,text:'INR'},ticks:{callback:short}};options.scales.y={grid:{display:false},ticks:{font:{size:11},callback:function(v){const label=this.getLabelForValue(v);return label.length>23?label.slice(0,22)+'...':label;}}};options.plugins.tooltip={callbacks:{label:c=>rupee(c.parsed.x)}};
    draw('rankChart','bar',{labels:ranked.map(([n])=>n),datasets:[{label:'Revenue',data:ranked.map(([,r])=>r.total/100),backgroundColor:ranked.map((_,i)=>palette[i%palette.length]),barThickness:13,borderRadius:2}]},options);
    options=base();options.scales.x.stacked=true;options.scales.y.stacked=true;options.scales.y.title={display:true,text:'INR'};options.plugins.legend.display=true;options.plugins.legend.position='bottom';options.plugins.tooltip={callbacks:{label:c=>c.dataset.label+': '+rupee(c.parsed.y)}};
    draw('mixChart','bar',{labels,datasets:[{label:'Ad revenue',data:a.dates.map(([,v])=>v.ad/100),backgroundColor:palette[1]},{label:'Sponsorship / others',data:a.dates.map(([,v])=>v.other/100),backgroundColor:palette[2]}]},options);
  }
  function expand(id){const source=charts[id];if(!source)return;document.getElementById('expandedTitle').textContent=document.getElementById(id).closest('.chart-block').querySelector('h3').textContent;document.getElementById('chartDialog').showModal();if(expanded)expanded.destroy();expanded=new Chart(document.getElementById('expandedChart'),{type:source.config.type,data:source.config.data,options:{...source.config.options,responsive:true,maintainAspectRatio:false},plugins:[emptyPlugin]});}
  function close(){document.getElementById('chartDialog').close();if(expanded){expanded.destroy();expanded=null;}}
  document.querySelectorAll('[data-expand]').forEach(b=>b.addEventListener('click',()=>expand(b.dataset.expand)));
  document.getElementById('closeChart').addEventListener('click',close);
  document.getElementById('chartDialog').addEventListener('close',()=>{if(expanded){expanded.destroy();expanded=null;}});
  for(const id of ['trendMetric','interval','rankLimit'])document.getElementById(id).addEventListener('change',()=>render());
  return{render,aggregate,charts};
})();

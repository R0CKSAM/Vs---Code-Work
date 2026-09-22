'use strict';
// All charts consume the same already-authorized, applied report rows.
window.RevenueCharts=(()=>{
  const palette=['#087f68','#328db5','#bd7e16','#9258a9','#d36c70','#568148','#5368ba','#627b89'];
  const charts={};let rows=[],expanded=null;
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
    if(!rows.length){Object.values(charts).forEach(c=>c.destroy());for(const k in charts)delete charts[k];return;}
    const labels=a.dates.map(([d])=>interval==='week'?'Week of '+d:d);
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

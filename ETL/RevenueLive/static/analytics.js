'use strict';
// All charts consume the same already-authorized, applied report rows.
window.RevenueCharts=(()=>{
  const palette=['#087f68','#328db5','#bd7e16','#9258a9','#d36c70','#568148','#5368ba','#627b89'];
  const charts={};let rows=[],expanded=null;
  const fmt=n=>new Intl.NumberFormat('en-IN').format(n);
  const rupee=n=>new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:2}).format(n);
  const short=n=>new Intl.NumberFormat('en-IN',{notation:'compact',maximumFractionDigits:1}).format(n);
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
      x:{grid:{display:false},ticks:{color:'#65737b',maxRotation:0,autoSkip:true,maxTicksLimit:8}},
      y:{beginAtZero:true,border:{display:false},grid:{color:'#e1e7e9'},ticks:{color:'#65737b',callback:short}}
    }
  };}
  function draw(id,type,data,options){if(charts[id])charts[id].destroy();charts[id]=new Chart(document.getElementById(id),{type,data,options,plugins:[emptyPlugin]});}
  function render(values=rows){
    rows=values;const interval=document.getElementById('interval').value,metric=document.getElementById('trendMetric').value;
    const a=aggregate(rows,interval),monetary=['total','ad'].includes(metric),divisor=monetary?100:1;
    document.getElementById('chartsEmpty').hidden=rows.length>0;document.getElementById('chartGrid').hidden=rows.length===0;
    if(!rows.length){Object.values(charts).forEach(c=>c.destroy());for(const k in charts)delete charts[k];return;}
    const labels=a.dates.map(([d])=>interval==='week'?'Week of '+d:d);
    let options=base();options.scales.y.title={display:true,text:monetary?'INR':metric==='views'?'Views':'Ad impressions'};options.plugins.tooltip={callbacks:{label:c=>(monetary?rupee:fmt)(c.parsed.y)}};
    draw('trendChart','line',{labels,datasets:[{label:metric,data:a.dates.map(([,v])=>v[metric]/divisor),borderColor:palette[0],backgroundColor:'#087f6812',fill:true,tension:.15,pointRadius:labels.length>40?0:3,pointHoverRadius:6,borderWidth:2}]},options);
    const top=a.channels.slice(0,6);if(a.channels.length>6)top.push(['Other selected channels',{total:a.channels.slice(6).reduce((n,[,r])=>n+r.total,0)}]);
    const revenue=top.map(([,r])=>r.total/100),total=revenue.reduce((n,v)=>n+v,0);
    options={responsive:true,maintainAspectRatio:false,animation:false,cutout:'65%',plugins:{
      legend:{position:'right',labels:{boxWidth:10,font:{size:11},generateLabels:chart=>chart.data.labels.map((text,i)=>({text:text.length>24?text.slice(0,23)+'...':text,fillStyle:chart.data.datasets[0].backgroundColor[i],strokeStyle:'transparent',index:i}))}},
      tooltip:{callbacks:{label:c=>`${c.label}: ${rupee(c.raw)} (${total?(c.raw/total*100).toFixed(1):'0.0'}%)`}}
    }};
    const shareType=document.getElementById('shareType').value;
    options.cutout=shareType==='pie'?0:'65%';options.plugins.legend.onClick=()=>{};
    draw('shareChart',shareType,{labels:top.map(([name])=>name),datasets:[{data:revenue,backgroundColor:palette,borderWidth:2,borderColor:'#f4f6f7'}]},options);
    document.getElementById('shareNote').textContent=a.channels.length>6?'Top 6 channels; remaining selected channels grouped as Other.':'Share of selected-channel revenue.';
    const limit=document.getElementById('rankLimit').value,ranked=limit==='all'?a.channels:a.channels.slice(0,Number(limit));
    document.getElementById('rankFrame').style.height=Math.max(290,ranked.length*31)+'px';
    options=base();options.indexAxis='y';options.scales.x={beginAtZero:true,grid:{color:'#e1e7e9'},title:{display:true,text:'INR'},ticks:{callback:short}};options.scales.y={grid:{display:false},ticks:{font:{size:11},callback:function(v){const label=this.getLabelForValue(v);return label.length>23?label.slice(0,22)+'...':label;}}};options.plugins.tooltip={callbacks:{label:c=>rupee(c.parsed.x)}};
    draw('rankChart','bar',{labels:ranked.map(([n])=>n),datasets:[{label:'Revenue',data:ranked.map(([,r])=>r.total/100),backgroundColor:ranked.map((_,i)=>palette[i%palette.length]),barThickness:13,borderRadius:2}]},options);
    options=base();options.scales.x.stacked=true;options.scales.y.stacked=true;options.scales.y.title={display:true,text:'INR'};options.plugins.legend.display=true;options.plugins.legend.position='bottom';options.plugins.tooltip={callbacks:{label:c=>c.dataset.label+': '+rupee(c.parsed.y)}};
    draw('mixChart','bar',{labels,datasets:[{label:'Ad revenue',data:a.dates.map(([,v])=>v.ad/100),backgroundColor:palette[1]},{label:'Sponsorship / others',data:a.dates.map(([,v])=>v.other/100),backgroundColor:palette[2]}]},options);
    options=base();options.interaction={mode:'nearest',intersect:true};options.scales.x={type:'linear',beginAtZero:true,title:{display:true,text:'Views'},grid:{color:'#e1e7e9'},ticks:{callback:short}};options.scales.y.title={display:true,text:'Revenue (INR)'};options.plugins.tooltip={callbacks:{label:c=>`${c.raw.name}: ${fmt(c.raw.x)} views | ${rupee(c.raw.y)}`}};
    draw('scatterChart','scatter',{datasets:[{label:'Channels',data:a.channels.map(([name,v])=>({x:v.views,y:v.total/100,name})),backgroundColor:a.channels.map((_,i)=>palette[i%palette.length]),pointRadius:7,pointHoverRadius:10}]},options);
  }
  function expand(id){const source=charts[id];if(!source)return;document.getElementById('expandedTitle').textContent=document.getElementById(id).closest('.chart-block').querySelector('h3').textContent;document.getElementById('chartDialog').showModal();if(expanded)expanded.destroy();expanded=new Chart(document.getElementById('expandedChart'),{type:source.config.type,data:source.config.data,options:{...source.config.options,responsive:true,maintainAspectRatio:false},plugins:[emptyPlugin]});}
  function close(){document.getElementById('chartDialog').close();if(expanded){expanded.destroy();expanded=null;}}
  document.querySelectorAll('[data-expand]').forEach(b=>b.addEventListener('click',()=>expand(b.dataset.expand)));
  document.getElementById('closeChart').addEventListener('click',close);
  document.getElementById('chartDialog').addEventListener('close',()=>{if(expanded){expanded.destroy();expanded=null;}});
  for(const id of ['trendMetric','interval','rankLimit','shareType'])document.getElementById(id).addEventListener('change',()=>render());
  return{render,aggregate,charts};
})();

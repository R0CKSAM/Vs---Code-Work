'use strict';
window.ChannelComparison=(()=>{
  const metrics={views:'Views',impressions:'Ad impressions',ad:'Ad revenue',other:'Sponsorship / others',total:'Total revenue'};
  const palette=['#1769d5','#b72e75','#008777','#aa6018','#7448bc','#31566f'];
  let section,chart,rows=[],selected=new Set(),parameters=new Set(['views']),initialized=false;
  function checkbox(value,label,checked,onChange){
    const wrapper=document.createElement('label'),input=document.createElement('input'),text=document.createElement('span');
    input.type='checkbox';input.value=value;input.checked=checked;text.textContent=label;
    input.addEventListener('change',()=>onChange(input.checked));wrapper.append(input,text);return wrapper;
  }
  function mount(){
    if(section)return;
    section=document.createElement('section');section.id='channelComparison';
    section.innerHTML='<h2>Channel comparison</h2><div class="comparison-controls"><details><summary>Channels</summary><div class="comparison-channel-options"></div></details><fieldset><legend>Parameters</legend><div class="comparison-parameters"></div></fieldset></div><p class="comparison-status" role="status"></p><div class="comparison-canvas"><canvas id="channelComparisonCanvas" role="img" aria-label="Daily channel comparison"></canvas></div>';
    document.getElementById('viewsDistribution').after(section);
    for(const [key,label] of Object.entries(metrics))section.querySelector('.comparison-parameters').append(checkbox(key,label,parameters.has(key),checked=>{checked?parameters.add(key):parameters.delete(key);draw();}));
  }
  function draw(){
    chart?.destroy();chart=null;
    section.querySelector('summary').textContent='Channels ('+selected.size+')';
    const status=section.querySelector('.comparison-status'),frame=section.querySelector('.comparison-canvas');
    frame.hidden=!rows.length||!selected.size||!parameters.size;
    if(frame.hidden){status.textContent=!rows.length?'No data in the selected range.':!selected.size?'Select channels to compare.':'Select at least one parameter.';return;}
    const reported=rows.map(r=>r.day).sort(),start=document.getElementById('start').value||reported[0],end=document.getElementById('end').value||reported.at(-1),days=[];
    for(let time=Date.parse(start+'T00:00:00Z');time<=Date.parse(end+'T00:00:00Z');time+=86400000)days.push(new Date(time).toISOString().slice(0,10));
    const sums=new Map();
    for(const row of rows){if(!selected.has(row.channel))continue;if(!sums.has(row.channel))sums.set(row.channel,new Map());const byDay=sums.get(row.channel);if(!byDay.has(row.day))byDay.set(row.day,Object.fromEntries(Object.keys(metrics).map(key=>[key,0])));for(const key of Object.keys(metrics))byDay.get(row.day)[key]+=row[key];}
    let missing=false;const datasets=[];
    for(const [index,name] of [...selected].entries())for(const key of parameters){
      const money=!['views','impressions'].includes(key),metricIndex=Object.keys(metrics).indexOf(key);
      const data=days.map(day=>{const value=sums.get(name)?.get(day);if(!value){missing=true;return null;}return value[key]/(money?100:1);});
      datasets.push({label:name+' - '+metrics[key],data,yAxisID:money?'money':'count',borderColor:palette[index%palette.length],backgroundColor:palette[index%palette.length],borderDash:[[],[7,4],[2,3],[10,3,2,3],[12,5]][metricIndex],pointStyle:['circle','rect','triangle','rectRot','crossRot'][metricIndex],borderWidth:2,pointRadius:days.length>60?1:3,tension:0,spanGaps:false});
    }
    status.textContent=missing?'Some channel-day records are missing.':days.length===1?'One reporting date selected.':'';
    const count=datasets.some(d=>d.yAxisID==='count'),money=datasets.some(d=>d.yAxisID==='money');
    chart=new Chart(section.querySelector('canvas'),{type:'line',data:{labels:days,datasets},options:{responsive:true,maintainAspectRatio:false,animation:false,interaction:{mode:'index',intersect:false},scales:{x:{ticks:{maxTicksLimit:10}},count:{display:count,position:'left',beginAtZero:true,title:{display:true,text:'Count'},ticks:{precision:0}},money:{display:money,position:count?'right':'left',beginAtZero:true,title:{display:true,text:'Revenue (INR)'},grid:{drawOnChartArea:!count}}},plugins:{legend:{position:'bottom',labels:{usePointStyle:true,font:{size:13}}},tooltip:{callbacks:{label:context=>context.dataset.label+': '+new Intl.NumberFormat('en-IN',context.dataset.yAxisID==='money'?{style:'currency',currency:'INR',maximumFractionDigits:2}:{maximumFractionDigits:0}).format(context.parsed.y)}}}}});
  }
  function render(data){
    mount();rows=data;
    const names=[...new Set(rows.map(r=>r.channel))].sort();
    selected=new Set([...selected].filter(name=>names.includes(name)));
    if(!initialized&&names.length){selected=new Set(names.slice(0,2));initialized=true;}
    if(!names.length)initialized=false;
    section.querySelector('.comparison-channel-options').replaceChildren(...names.map(name=>checkbox(name,name,selected.has(name),checked=>{checked?selected.add(name):selected.delete(name);draw();})));
    draw();
  }
  return {render};
})();

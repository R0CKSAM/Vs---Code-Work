'use strict';
window.RevenueShare=(()=>{
  let redrawTree=()=>{};
  let selectedMetric='total',currentRows=[];
  let timelineMode='auto',drillRange=null;
  const hiddenTimelineSeries=new Set();
  const metricNames={total:'Revenue',views:'Views',impressions:'Ad impressions'};
  const metricValue=value=>selectedMetric==='total'?cash(value):new Intl.NumberFormat('en-IN').format(value);
  let channelChanges=new Map();
  function applyChannelChanges(){
    document.querySelectorAll('.channel-comparison').forEach(node=>node.remove());
    for(const node of document.querySelectorAll('#channelMetrics tbody tr,#viewsTree .views-tree-tile')){
      const name=node.querySelector('.channel-brand')?.dataset.channelName,key=node.matches('tr')?'total':'views',change=channelChanges.get(name)?.[key];
      if(!Number.isFinite(change))continue;
      const badge=document.createElement('span');badge.className='channel-comparison '+(change<0?'down':'up');badge.textContent=(change<0?'\u2193 ':change>0?'\u2191 ':'')+Math.abs(change).toFixed(1)+'%';badge.title='Compared with the preceding equal-length period';
      (node.matches('tr')?node.lastElementChild:node).append(badge);
    }
  }
  function compare(current,previous,complete){
    channelChanges.clear();
    metricsExpanded=false;
    if(complete){
      const sums=rows=>{const map=new Map();for(const r of rows){if(!map.has(r.channel))map.set(r.channel,{total:0,views:0});for(const key of ['total','views'])map.get(r.channel)[key]+=r[key];}return map;};
      const before=sums(previous.rows);
      for(const [name,values] of sums(current.rows)){const old=before.get(name);if(!old)continue;const changes={};for(const key of ['total','views'])if(old[key]!==0)changes[key]=(values[key]-old[key])/Math.abs(old[key])*100;channelChanges.set(name,changes);}
    }
    applyChannelChanges();
  }
  window.addEventListener('resize',()=>requestAnimationFrame(()=>redrawTree()));
  const colors=['#f8cf96','#f990ad','#a8c7ec','#c9b1e5','#8dd4bf','#91b9cd'];
  // Draw the existing arcs beneath their faces; data angles remain unchanged.
  const raisedRing={id:'raisedRing',beforeDatasetsDraw(chart){
    const ctx=chart.ctx;ctx.save();
    for(let depth=7;depth>0;depth--){
      chart.getDatasetMeta(0).data.forEach((arc,index)=>{
        const {x,y,innerRadius,outerRadius,startAngle,endAngle}=arc;
        if(!outerRadius||endAngle<=startAngle)return;
        const color=colors[index%colors.length];
        const rgb=[1,3,5].map(offset=>Math.round(parseInt(color.slice(offset,offset+2),16)*.72));
        ctx.fillStyle='rgb('+rgb.join(',')+')';ctx.beginPath();
        ctx.arc(x,y+depth,outerRadius,startAngle,endAngle);
        ctx.arc(x,y+depth,innerRadius,endAngle,startAngle,true);
        ctx.closePath();ctx.fill();
      });
    }
    ctx.restore();
  },afterDraw(chart){
    const arc=chart.getDatasetMeta(0).data[0],centre=document.querySelector('#revenueShare .share-centre');
    const radius=arc?.innerRadius||chart.width*.3;
    // Keep the entire text block inside the circular opening, including its raised lip.
    Object.assign(centre.style,{inset:'auto',left:(arc?.x??chart.width/2)+'px',top:((arc?.y??chart.height/2)+3)+'px',width:Math.max(20,radius*1.4-6)+'px',height:Math.max(20,radius-4)+'px',padding:'0',transform:'translate(-50%,-50%)'});
    for(const [index,label] of [...centre.children].entries()){
      let size=index===0?22:11;label.style.fontSize=size+'px';
      while((label.scrollWidth>label.clientWidth||centre.scrollHeight>centre.clientHeight)&&size>6){size-=.5;label.style.fontSize=size+'px';}
    }
  }};
  const channelIcon=name=>/music|9xm|tashan|jhakaas|jalwa/i.test(name)?'music-2':/kids/i.test(name)?'smile':/bhojpuri|bollywood/i.test(name)?'clapperboard':'tv-minimal';
  let channelLogos={};
  let channelBrands=new Map();
  function setChannels(channels){
    channelBrands=new Map(channels.map(channel=>[channel.name.trim().toLowerCase(),channel]));
    document.querySelectorAll('.channel-brand').forEach(target=>brandLogo(target,target.dataset.channelName));
  }
  function brandLogo(target,name,override){
    target.dataset.channelName=name;target.classList.add('channel-brand');
    const initials=name.trim().split(/\s+/).slice(0,2).map(word=>word[0]).join('').toUpperCase();
    target.textContent=initials;target.setAttribute('aria-hidden','true');
    const channel=override||channelBrands.get(name.trim().toLowerCase());
    const asset=channelLogos[(channel?.logo_name||name).trim().toLowerCase()];
    target.style.backgroundColor=asset?.background||'#fff';
    const custom=channel?.logo_url&&/^\/api\/channels\/\d+\/logo\?v=[a-f0-9]{64}$/.test(channel.logo_url)?channel.logo_url:null;
    if(!custom&&(!asset||! /^[a-z0-9]+\.png$/.test(asset.file)))return;
    const image=document.createElement('img');image.alt='';image.width=44;image.height=32;
    image.onerror=()=>{target.style.backgroundColor='#fff';target.replaceChildren(document.createTextNode(initials));};
    image.src=custom||'/static/channel-logos/'+asset.file;target.replaceChildren(image);
  }
  fetch('/static/channel-logos/manifest.json').then(response=>{if(!response.ok)throw new Error('Logo manifest unavailable');return response.json();}).then(manifest=>{
    channelLogos=manifest;
    document.querySelectorAll('.channel-brand').forEach(target=>brandLogo(target,target.dataset.channelName));
  }).catch(()=>{});
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
  const cash=value=>new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:1,minimumFractionDigits:1}).format(value/100);
  const percent=(value,total)=>{
    if(!(total>0)||!(value>0))return '0%';
    const share=value/total*100;
    if(share<0.1)return '<0.1%';
    if(share>99.9&&value<total)return '>99.9%';
    return new Intl.NumberFormat('en-IN',{maximumFractionDigits:1}).format(share)+'%';
  };
  const trigger=document.createElement('button');trigger.type='button';trigger.id='revenueShare';trigger.setAttribute('aria-expanded','false');trigger.setAttribute('aria-controls','revenueShareExpanded');trigger.setAttribute('aria-label','Revenue share: expand all channels');
  trigger.innerHTML='<span class="share-title">Revenue share <span aria-hidden="true">&#8599;</span></span><span class="share-content"><span class="share-ring"><canvas id="summaryShareCanvas" aria-hidden="true"></canvas><span class="share-centre"><strong id="shareSum"></strong><span>Total revenue</span></span></span><span id="summaryShareLegend"></span></span><span id="shareMessage"></span>';
  document.querySelector('#dashboard .metrics').after(trigger);
  const modal=document.createElement('section');modal.id='revenueShareExpanded';modal.hidden=true;modal.setAttribute('aria-labelledby','revenueShareTitle');modal.innerHTML='<div class="share-dialog-heading"><h2 id="revenueShareTitle">Revenue by channel</h2><button type="button" aria-label="Collapse channel distribution" title="Collapse">&#8722;</button></div><div id="fullShareRows"></div>';
  trigger.after(modal);
  const overview=document.createElement('div');overview.id='revenueOverview';trigger.before(overview);overview.append(trigger,modal);
  const trend=document.createElement('section');trend.className='daily-revenue';trend.innerHTML='<h2>Revenue over time</h2><div class="daily-revenue-canvas"><canvas id="dailyRevenueCanvas" role="img" aria-label="Daily ad and sponsorship revenue"></canvas></div><p id="dailyRevenueNote"></p>';overview.append(trend);
  const trendHeader=document.createElement('div');trendHeader.className='trend-header';
  const metricSelector=document.createElement('div');metricSelector.className='overview-metric-selector';metricSelector.setAttribute('role','group');metricSelector.setAttribute('aria-label','Timeline and channel share metric');
  for(const [key,name] of Object.entries(metricNames)){
    const button=document.createElement('button');button.type='button';button.textContent=name;button.dataset.metric=key;button.setAttribute('aria-pressed',String(key===selectedMetric));
    button.addEventListener('click',()=>{if(selectedMetric===key)return;selectedMetric=key;const changes=new Map(channelChanges);render(currentRows);channelChanges=changes;applyChannelChanges();});metricSelector.append(button);
  }
  trendHeader.append(trend.querySelector('h2'),metricSelector);trend.prepend(trendHeader);
  const expandTimeline=document.createElement('button');expandTimeline.type='button';expandTimeline.className='timeline-expand';expandTimeline.title='Expand timeline';expandTimeline.setAttribute('aria-label','Expand timeline');expandTimeline.setAttribute('aria-haspopup','dialog');expandTimeline.innerHTML='<i data-lucide="maximize-2" aria-hidden="true"></i>';trendHeader.append(expandTimeline);
  const timelineDialog=document.createElement('dialog');timelineDialog.id='timelineDetailDialog';timelineDialog.setAttribute('aria-labelledby','timelineDetailTitle');
  timelineDialog.innerHTML='<div class="timeline-dialog-heading"><h2 id="timelineDetailTitle"></h2><button type="button" aria-label="Close expanded timeline" title="Close"><i data-lucide="x" aria-hidden="true"></i></button></div>';
  document.body.append(timelineDialog);
  const timelineFrame=trend.querySelector('.daily-revenue-canvas');
  const timelineContent=document.createElement('div');timelineContent.className='timeline-content';
  const timelineControls=document.createElement('div');timelineControls.className='timeline-controls';
  const intervalSelector=document.createElement('div');intervalSelector.className='timeline-intervals';intervalSelector.setAttribute('role','group');intervalSelector.setAttribute('aria-label','Timeline interval');
  for(const [value,label] of [['auto','Auto'],['day','Daily'],['week','Weekly'],['month','Monthly']]){
    const button=document.createElement('button');button.type='button';button.textContent=label;button.dataset.timelineInterval=value;
    button.addEventListener('click',()=>{timelineMode=value;drillRange=null;renderTimeline();});intervalSelector.append(button);
  }
  const periodPicker=document.createElement('select');periodPicker.id='timelinePeriod';periodPicker.setAttribute('aria-label','Open period daily breakdown');
  periodPicker.addEventListener('change',()=>{if(periodPicker.value!=='')drillInto(Number(periodPicker.value));});
  const backTimeline=document.createElement('button');backTimeline.type='button';backTimeline.id='timelineBack';backTimeline.innerHTML='<i data-lucide="arrow-left" aria-hidden="true"></i>Full range';backTimeline.title='Back to the full selected range';
  backTimeline.addEventListener('click',()=>{drillRange=null;renderTimeline();periodPicker.focus();});
  const timelineScope=document.createElement('span');timelineScope.id='timelineScope';timelineScope.setAttribute('role','status');
  timelineControls.append(intervalSelector,periodPicker,backTimeline,timelineScope);
  timelineContent.append(timelineControls,timelineFrame,document.getElementById('dailyRevenueNote'),document.getElementById('revenueFinalization'));trend.append(timelineContent);
  expandTimeline.addEventListener('click',()=>{
    document.getElementById('timelineDetailTitle').textContent=metricNames[selectedMetric]+' over time';
    timelineDialog.append(timelineContent);timelineDialog.showModal();lineChart?.resize();
  });
  timelineDialog.querySelector('button').addEventListener('click',()=>timelineDialog.close());
  timelineDialog.addEventListener('close',()=>{trend.append(timelineContent);lineChart?.resize();expandTimeline.focus({preventScroll:true});});
  const views=document.createElement('section');views.id='viewsDistribution';views.innerHTML='<p id="viewsDistributionEmpty"></p>';overview.after(views);
  const metrics=document.createElement('section');metrics.id='channelMetrics';metrics.innerHTML='<h2>Channel metrics</h2><div class="metrics-table-scroll"><table><thead><tr><th scope="col">Channel</th><th scope="col">Views</th><th scope="col">Ad impressions</th><th scope="col">Ad revenue</th><th scope="col">Sponsorship / others</th><th scope="col">Total revenue</th></tr></thead><tbody></tbody></table></div><p class="metrics-empty"></p>';views.before(metrics);
  const metricsToggle=document.createElement('button');metricsToggle.type='button';metricsToggle.className='metrics-others';metricsToggle.setAttribute('aria-expanded','false');metricsToggle.setAttribute('aria-controls','channelMetricsBody');metrics.querySelector('.metrics-table-scroll').after(metricsToggle);metrics.querySelector('tbody').id='channelMetricsBody';let metricsExpanded=false;
  function sizeMetrics(){const rows=[...metrics.querySelectorAll('tbody tr')],remaining=Math.max(0,rows.length-5);rows.forEach((row,i)=>row.hidden=!metricsExpanded&&i>=5);metricsToggle.hidden=!remaining;metricsToggle.setAttribute('aria-expanded',String(metricsExpanded));metricsToggle.replaceChildren();const text=document.createElement('span');text.textContent=metricsExpanded?'Show Top 5':'Others ('+remaining+')';const glyph=document.createElement('i');glyph.dataset.lucide=metricsExpanded?'chevron-up':'chevron-down';glyph.setAttribute('aria-hidden','true');metricsToggle.append(text,glyph);window.lucide?.createIcons();}
  metricsToggle.addEventListener('click',()=>{metricsExpanded=!metricsExpanded;sizeMetrics();});
  const treeButton=document.createElement('div');treeButton.id='viewsTreeButton';treeButton.innerHTML='<h2 class="share-title">Views distribution</h2><span id="viewsTree"></span>';
  views.prepend(treeButton);
  const treeLegend=document.createElement('span');treeLegend.id='viewsTreeLegend';treeButton.append(treeLegend);
  for(const button of [modal.querySelector('button')]){button.classList.add('distribution-collapse');button.setAttribute('aria-label','Collapse distribution');button.title='Collapse distribution';button.innerHTML='<i data-lucide="minimize-2" aria-hidden="true"></i>';}
  trigger.querySelector('.share-title>span').innerHTML='<i data-lucide="maximize-2" aria-hidden="true"></i>';trigger.title='Expand distribution';
  window.lucide?.createIcons();
  document.addEventListener('keydown',event=>{if(event.key!=='Escape'||channelDialog.open||timelineDialog.open)return;if(!modal.hidden){collapse();trigger.focus();}});
  const channelDialog=document.createElement('dialog');channelDialog.id='channelDetailDialog';channelDialog.setAttribute('aria-labelledby','channelDetailTitle');
  channelDialog.innerHTML='<div class="channel-detail-heading"><div><h2 id="channelDetailTitle"></h2><p id="channelDetailRange"></p></div><button type="button" aria-label="Close channel details" title="Close"><i data-lucide="x" aria-hidden="true"></i></button></div><dl class="channel-detail-totals"></dl><p id="channelDetailCoverage"></p><div class="channel-detail-table"><table><thead><tr><th scope="col">Date</th><th scope="col">Views</th><th scope="col">Ad impressions</th><th scope="col">Ad revenue</th><th scope="col">Sponsorship / others</th><th scope="col">Total revenue</th></tr></thead><tbody></tbody></table></div>';
  document.body.append(channelDialog);channelDialog.querySelector('button').addEventListener('click',()=>channelDialog.close());window.lucide?.createIcons();
  const detailActions=document.createElement('div');detailActions.className='channel-detail-actions';
  const detailDownload=document.createElement('button');detailDownload.type='button';detailDownload.title='Download channel CSV';detailDownload.setAttribute('aria-label','Download channel CSV');detailDownload.innerHTML='<i data-lucide="download" aria-hidden="true"></i>';
  const detailClose=channelDialog.querySelector('button');detailClose.before(detailActions);detailActions.append(detailDownload,detailClose);window.lucide?.createIcons();
  let detailExport=null;
  channelDialog.addEventListener('close',()=>{detailExport=null;});
  detailDownload.addEventListener('click',()=>{
    if(!detailExport)return;
    const {name,first,last,days}=detailExport;
    const safeName=/^[\s]*[=+@\-\t\r\n]/.test(name)?"'"+name:name;
    const records=[['Date','Channel','Views','Ad impressions','Ad revenue (INR)','Sponsorship / others (INR)','Total revenue (INR)'],...days.map(([day,value])=>[day,safeName,value.views,value.impressions,(value.ad/100).toFixed(2),(value.other/100).toFixed(2),(value.total/100).toFixed(2)])];
    const csv=records.map(record=>record.map(value=>'"'+String(value).replace(/"/g,'""')+'"').join(',')).join('\r\n');
    const url=URL.createObjectURL(new Blob(['\uFEFF'+csv],{type:'text/csv;charset=utf-8;'})),link=document.createElement('a');
    link.href=url;link.download=(name.replace(/[^a-z0-9_-]+/gi,'-').slice(0,80)||'channel')+'_'+first+'_'+last+'.csv';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
  function openChannel(name){
    const rows=currentRows.filter(row=>row.channel===name),days=new Map(),keys=['views','impressions','ad','other','total'],labels=['Views','Ad impressions','Ad revenue','Sponsorship / others','Total revenue'];
    for(const row of rows){if(!days.has(row.day))days.set(row.day,Object.fromEntries(keys.map(key=>[key,0])));for(const key of keys)days.get(row.day)[key]+=row[key];}
    const sorted=[...days].sort(([a],[b])=>a.localeCompare(b)),first=document.getElementById('start').value||sorted[0]?.[0],last=document.getElementById('end').value||sorted.at(-1)?.[0];
    detailExport={name,first,last,days:sorted};detailDownload.disabled=!sorted.length;
    const dateLabel=day=>new Intl.DateTimeFormat('en-GB',{day:'2-digit',month:'short',year:'numeric',timeZone:'UTC'}).format(new Date(day+'T00:00:00Z'));
    document.getElementById('channelDetailTitle').textContent=name;
    document.getElementById('channelDetailRange').textContent=first&&last?dateLabel(first)+' - '+dateLabel(last):'Selected range';
    const format=(value,index)=>index<2?new Intl.NumberFormat('en-IN').format(value):cash(value);
    channelDialog.querySelector('dl').replaceChildren(...keys.map((key,index)=>{const item=document.createElement('div'),label=document.createElement('dt'),value=document.createElement('dd');label.textContent=labels[index];value.textContent=format(rows.reduce((sum,row)=>sum+row[key],0),index);item.append(label,value);return item;}));
    channelDialog.querySelector('tbody').replaceChildren(...sorted.map(([day,values])=>{const row=document.createElement('tr'),date=document.createElement('th');date.scope='row';date.textContent=dateLabel(day);row.append(date);keys.forEach((key,index)=>{const cell=document.createElement('td');cell.textContent=format(values[key],index);row.append(cell);});return row;}));
    const expected=first&&last?Math.round((Date.parse(last)-Date.parse(first))/86400000)+1:days.size;
    document.getElementById('channelDetailCoverage').textContent=!rows.length?'No records for this channel in the selected range.':days.size<expected?days.size+' of '+expected+' days reported. Missing dates are not counted as zero.':'';
    channelDialog.showModal();
  }
  let lineChart=null;
  let timelineBuckets=[];
  const timelineDate=(day,options={day:'2-digit',month:'short',year:'numeric'})=>new Intl.DateTimeFormat('en-GB',{...options,timeZone:'UTC'}).format(new Date(day+'T00:00:00Z'));
  const compactNumber=value=>{
    const absolute=Math.abs(value),unit=absolute>=1e7?[1e7,'Cr']:absolute>=1e5?[1e5,'L']:absolute>=1e3?[1e3,'K']:[1,''];
    return new Intl.NumberFormat('en-IN',{maximumFractionDigits:unit[0]===1?0:1}).format(value/unit[0])+unit[1];
  };
  function drillInto(index){
    const bucket=timelineBuckets[index];if(!bucket||bucket.missing||bucket.start===bucket.end)return;
    drillRange={start:bucket.start,end:bucket.end};renderTimeline();backTimeline.focus({preventScroll:true});
  }
  function renderTimeline(){
    const isRevenue=selectedMetric==='total',metricName=metricNames[selectedMetric];
    const model=window.RevenueTimelineData.aggregate(currentRows,{
      start:drillRange?.start||document.getElementById('start').value,
      end:drillRange?.end||document.getElementById('end').value,
      mode:drillRange?'day':timelineMode,
      channelCount:document.querySelectorAll('#channelOptions input:checked').length
    });
    const {interval,buckets}=model;timelineBuckets=buckets;
    const intervalName={day:'Daily',week:'Weekly',month:'Monthly'}[interval];
    intervalSelector.querySelectorAll('button').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.timelineInterval===timelineMode)));
    backTimeline.hidden=!drillRange;periodPicker.hidden=!!drillRange||interval==='day'||!buckets.length;
    const placeholder=document.createElement('option');placeholder.value='';placeholder.textContent='Open period...';
    periodPicker.replaceChildren(placeholder,...buckets.map((bucket,index)=>{
      const option=document.createElement('option');option.value=index;
      option.textContent=interval==='month'?timelineDate(bucket.periodStart,{month:'short',year:'numeric'}):timelineDate(bucket.start)+' - '+timelineDate(bucket.end);
      if(bucket.partial)option.textContent+=' (partial)';if(bucket.missing)option.textContent+=' (no data)';option.disabled=bucket.missing;return option;
    }));
    timelineScope.textContent=drillRange?'Daily breakdown: '+timelineDate(model.start)+' - '+timelineDate(model.end):intervalName+' totals'+(timelineMode==='auto'?' (Auto)':'');
    document.getElementById('timelineDetailTitle').textContent=metricName+' over time';
    const bars=isRevenue&&(interval!=='day'||buckets.length<=7)||buckets.length===1;
    const stacked=bars&&isRevenue;
    const series=isRevenue?[['Ad revenue','ad','#09aaa1'],['Sponsorship / others','other','#fa668c']]:[[metricName,selectedMetric,selectedMetric==='views'?'#3689ef':'#d68a28']];
    const datasets=series.map(([label,key,color])=>({label,metricKey:key,
      data:buckets.map(bucket=>bucket.missing?null:bucket.values[key]/(isRevenue?100:1)),
      hidden:hiddenTimelineSeries.has(key),borderColor:color,backgroundColor:bars?color:color+'16',
      borderWidth:bars?0:2,fill:!bars,tension:0,spanGaps:false,
      pointRadius:buckets.length>45?0:2,pointHoverRadius:5,pointHitRadius:8,
      borderRadius:4,maxBarThickness:56,borderSkipped:false
    }));
    if(lineChart)lineChart.destroy();
    lineChart=new Chart(document.getElementById('dailyRevenueCanvas'),{type:bars?'bar':'line',data:{labels:buckets.map(bucket=>bucket.start),datasets},options:{
      responsive:true,maintainAspectRatio:false,animation:false,interaction:{mode:'index',intersect:false},
      onClick:(event,_,chart)=>{if(interval==='day')return;const hit=chart.getElementsAtEventForMode(event,'nearest',{intersect:true},true)[0];if(hit)setTimeout(()=>{if(lineChart===chart)drillInto(hit.index);},0);},
      plugins:{legend:{position:'bottom',labels:{color:'#506889',usePointStyle:true,pointStyle:'circle',boxWidth:10,padding:16},
        onClick:(_,item,chartLegend)=>{const chart=chartLegend.chart,key=chart.data.datasets[item.datasetIndex].metricKey,visible=chart.isDatasetVisible(item.datasetIndex);if(visible)hiddenTimelineSeries.add(key);else hiddenTimelineSeries.delete(key);chart.setDatasetVisibility(item.datasetIndex,!visible);chart.update();}},
        tooltip:{callbacks:{
          title:items=>{const bucket=buckets[items[0]?.dataIndex];return bucket?timelineDate(bucket.start)+(bucket.end!==bucket.start?' - '+timelineDate(bucket.end):'')+(bucket.partial?' (partial period)':''):'';},
          label:ctx=>ctx.dataset.label+': '+(ctx.raw===null?'No data':isRevenue?cash(ctx.raw*100):new Intl.NumberFormat('en-IN').format(ctx.raw)),
          footer:items=>{const bucket=buckets[items[0]?.dataIndex];if(!bucket)return '';const notes=[];
            if(bucket.incomplete)notes.push(bucket.reportedRecords+' of '+bucket.expectedRecords+' channel-day records reported');
            if(interval!=='day'&&bucket.daily.length){const value=day=>isRevenue?day.ad+day.other:day[selectedMetric];const peak=bucket.daily.reduce((best,day)=>value(day)>value(best)?day:best);notes.push('Highest recorded day: '+timelineDate(peak.day)+' | '+(isRevenue?cash(value(peak)):new Intl.NumberFormat('en-IN').format(value(peak))));}
            return notes;}
        }}},
      scales:{x:{stacked,offset:bars,grid:{display:false},ticks:{color:'#506889',maxTicksLimit:8,maxRotation:0,font:{size:12},callback:function(value){const bucket=buckets[value];return bucket?(interval==='month'?timelineDate(bucket.periodStart,{month:'short',year:'2-digit'}):timelineDate(bucket.start,{day:'2-digit',month:'short'})):'';}}},
        y:{stacked,beginAtZero:true,title:{display:true,text:isRevenue?'Revenue (INR)':metricName,color:'#506889'},grid:{color:'#e6edf5'},ticks:{color:'#506889',maxTicksLimit:7,precision:0,callback:value=>(isRevenue?'\u20b9':'')+compactNumber(value)}}}
    }});
    const notes=[];
    if(!currentRows.length)notes.push('No data in this selection.');
    else{
      if(buckets.some(bucket=>bucket.partial))notes.push('Partial period within the selected dates.');
    }
    document.getElementById('dailyRevenueNote').textContent=notes.join(' ');
    document.getElementById('dailyRevenueCanvas').setAttribute('aria-label',intervalName+' '+metricName.toLowerCase()+' '+(bars?'bars':'line chart')+(drillRange?' for '+model.start+' to '+model.end:''));
  }
  let chart=null,entries=[],total=0;
  function collapse(){modal.hidden=true;trigger.hidden=false;trigger.setAttribute('aria-expanded','false');}
  modal.querySelector('button').addEventListener('click',()=>{collapse();trigger.focus();});
  trigger.addEventListener('click',()=>{modal.hidden=false;trigger.hidden=true;trigger.setAttribute('aria-expanded','true');modal.querySelector('button').focus({preventScroll:true});});
  function row(name,value,index,full=false){
    const el=document.createElement('span');el.className=full?'full-share-row':'compact-share-row';
    const label=document.createElement('span');label.className='share-channel';label.textContent=name;label.title=name;
    const values=document.createElement('strong');values.textContent=metricValue(value)+' | '+percent(value,total);
    if(!full){const amount=document.createElement('span'),badge=document.createElement('span');amount.textContent=metricValue(value);badge.className='share-percent';badge.textContent=percent(value,total);values.replaceChildren(amount,badge);}
    el.style.setProperty('--share-color',colors[index%colors.length]);el.append(label,values);
    {const track=document.createElement('span');track.className='distribution-track';track.setAttribute('aria-hidden','true');const fill=document.createElement('span');fill.style.width=(total>0?Math.max(0,value)/total*100:0)+'%';track.append(fill);el.append(track);}
    return el;
  }
  function render(rows){
    if(timelineDialog.open)timelineDialog.close();
    if(channelDialog.open)channelDialog.close();
    if(rows!==currentRows)drillRange=null;
    currentRows=rows;
    window.ChannelComparison.render(rows);
    const metricName=metricNames[selectedMetric],isRevenue=selectedMetric==='total';
    metricSelector.querySelectorAll('button').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.metric===selectedMetric)));
    trend.querySelector('h2').textContent=metricName+' over time';
    trigger.querySelector('.share-title').firstChild.textContent=metricName+' share ';
    trigger.setAttribute('aria-label',metricName+' share: expand all channels');
    document.getElementById('revenueShareTitle').textContent=metricName+' by channel';
    trigger.querySelector('.share-centre>span').textContent='Total '+metricName.toLowerCase();
    channelChanges.clear();
    metricsExpanded=false;
    renderSparks(rows);
    let insight=document.getElementById('performanceInsight');
    if(!insight){insight=document.createElement('section');insight.id='performanceInsight';const title=document.createElement('h2');title.textContent='AI Insights';const glyph=document.createElement('i');glyph.dataset.lucide='sparkles';glyph.setAttribute('aria-hidden','true');title.prepend(glyph);insight.append(title,document.createElement('p'));document.querySelector('#dashboard .metrics').after(insight);}
    insight.hidden=!rows.length;
    if(!insight.querySelector('.insight-growth-art')){const artwork=document.createElement('span');artwork.className='insight-growth-art';artwork.setAttribute('aria-hidden','true');const bars=document.createElement('span');bars.className='insight-growth-bars';for(const height of [10,15,20,29,39,48]){const bar=document.createElement('i');bar.style.height=height+'px';bars.append(bar);}const arrow=document.createElement('img');arrow.src='/static/insight-growth-arrow.svg';arrow.alt='';arrow.className='insight-growth-arrow';artwork.append(bars,arrow);insight.append(artwork);}
    const metricSums=new Map();for(const r of rows){if(!metricSums.has(r.channel))metricSums.set(r.channel,{views:0,impressions:0,ad:0,other:0,total:0});for(const key of ['views','impressions','ad','other','total'])metricSums.get(r.channel)[key]+=r[key];}
    const keys=['views','impressions','ad','other','total'];
    // Independent column scales use unrounded values and all selected channels.
    const scales=keys.map(key=>{const values=[...metricSums.values()].map(value=>value[key]).sort((a,b)=>a-b),length=values.length;return {minimum:values[0]??0,maximum:values.at(-1)??0,middle:length?(length%2?values[Math.floor(length/2)]:(values[length/2-1]+values[length/2])/2):0};});
    function heatColor(n,{minimum,maximum,middle}){let low,high,f;if(minimum===maximum){low=high=n===0?[248,105,107]:[255,235,132];f=0;}else if(n<=minimum){low=high=[248,105,107];f=0;}else if(n>=maximum){low=high=[99,190,123];f=0;}else if(n<=middle&&middle>minimum){low=[248,105,107];high=[255,235,132];f=(n-minimum)/(middle-minimum);}else{low=[255,235,132];high=[99,190,123];f=(n-middle)/(maximum-middle);}return 'rgb('+low.map((value,i)=>(value+(high[i]-value)*f).toFixed(3)).join(',')+')';}
    metrics.querySelector('tbody').replaceChildren(...[...metricSums].sort((a,b)=>b[1].total-a[1].total||a[0].localeCompare(b[0])).map(([name,values])=>{const tr=document.createElement('tr'),label=document.createElement('th');label.scope='row';label.textContent=name;tr.append(label);keys.forEach((key,i)=>{const cell=document.createElement('td'),n=values[key];cell.dataset.label=['Views','Ad impressions','Ad revenue','Sponsorship / others','Total revenue'][i];cell.textContent=i<2?new Intl.NumberFormat('en-IN').format(n):cash(n);cell.style.backgroundColor=heatColor(n,scales[i]);cell.style.color='#202a30';cell.title=cell.dataset.label+': independent column scale; minimum red, median yellow, maximum green. Equal nonzero values yellow; all-zero values red.';tr.append(cell);});return tr;}));
    for(const [index,label] of [...metrics.querySelectorAll('tbody th')].entries()){const name=document.createElement('span'),badge=document.createElement('span'),glyph=document.createElement('i');name.textContent=label.textContent;badge.className='channel-glyph';badge.style.backgroundColor=colors[index%colors.length]+'55';glyph.dataset.lucide=channelIcon(name.textContent);glyph.setAttribute('aria-hidden','true');badge.append(glyph);label.replaceChildren(badge,name);}
    const ranked=[...metricSums].sort((a,b)=>b[1].total-a[1].total||a[0].localeCompare(b[0]));
    window.QuickInsights?.paintStrip();
    metrics.querySelectorAll('tbody tr').forEach((tr,index)=>{
      const rank=document.createElement('small');rank.className='channel-rank';rank.textContent=index+1;tr.querySelector('th').prepend(rank);
      tr.querySelectorAll('td').forEach((cell,i)=>{
        const value=ranked[index][1][keys[i]],maximum=scales[i].maximum;
        cell.style.removeProperty('background-color');cell.style.removeProperty('color');cell.title=cell.dataset.label+': '+cell.textContent;
        const number=document.createElement('span');number.textContent=cell.textContent;
        const track=document.createElement('span'),fill=document.createElement('span');track.className='channel-value-track';track.setAttribute('aria-hidden','true');fill.style.width=(maximum>0?Math.max(0,value)/maximum*100:0)+'%';track.append(fill);cell.replaceChildren(number,track);
      });
    });
    window.lucide?.createIcons();sizeMetrics();
    metrics.querySelectorAll('tbody th').forEach(label=>brandLogo(label.querySelector('.channel-glyph'),label.lastElementChild.textContent));
    metrics.querySelector('.metrics-empty').textContent=rows.length?'':'No channel data for this selection.';
    const viewSums=new Map();
    for(const r of rows)viewSums.set(r.channel,(viewSums.get(r.channel)||0)+r.views);
    renderTimeline();
    const viewEntries=[...viewSums].sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0])),viewTotal=viewEntries.reduce((sum,[,n])=>sum+n,0);
    const tree=document.getElementById('viewsTree');tree.replaceChildren();
    const positive=viewEntries;
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
      for(const [index,element] of [...tree.children].entries()){
        brandLogo(element.querySelector('.tile-channel-icon'),positive[index][0]);
        element.setAttribute('role','button');element.tabIndex=0;element.setAttribute('aria-haspopup','dialog');element.setAttribute('aria-label','View daily metrics for '+positive[index][0]);
        element.addEventListener('click',()=>openChannel(positive[index][0]));
        element.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();openChannel(positive[index][0]);}});
      }
      applyChannelChanges();
      window.lucide?.createIcons();
    };
    redrawTree();
    document.getElementById('viewsDistributionEmpty').textContent=!viewEntries.length?'No views data in this selection.':viewTotal===0?'No views recorded.':'';
    const sums=new Map();for(const r of rows)sums.set(r.channel,(sums.get(r.channel)||0)+r[selectedMetric]);
    entries=[...sums].sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0]));total=entries.reduce((sum,[,value])=>sum+value,0);
    trigger.classList.toggle('few-channels',entries.length<=2);
    document.getElementById('fullShareRows').classList.toggle('many-channels',entries.length>8);
    const valid=total>0&&entries.every(([,value])=>value>=0);
    const shown=entries.slice(0,5);if(entries.length>5)shown.push(['Others ('+(entries.length-5)+')',entries.slice(5).reduce((sum,[,value])=>sum+value,0)]);
    document.getElementById('shareSum').textContent=metricValue(total);
    document.getElementById('shareSum').title=metricValue(total);
    document.getElementById('summaryShareLegend').replaceChildren(...shown.map(([name,value],i)=>row(name,value,i)));
    document.getElementById('fullShareRows').replaceChildren(...entries.map(([name,value],i)=>row(name,value,i,true)));
    document.getElementById('shareMessage').textContent=!rows.length?'No '+metricName.toLowerCase()+' data in this selection.':!valid?'Share chart unavailable for zero or negative '+metricName.toLowerCase()+'.':'';
    trigger.disabled=!entries.length;
    if(chart)chart.destroy();
    chart=new Chart(document.getElementById('summaryShareCanvas'),{type:'doughnut',plugins:[raisedRing],data:{labels:shown.map(([name])=>name),datasets:[{data:valid?shown.map(([,value])=>value):[],backgroundColor:colors,borderWidth:1,borderColor:'#fff',hoverOffset:0}]},options:{responsive:true,maintainAspectRatio:false,cutout:'66%',layout:{padding:{top:2,right:2,bottom:10,left:2}},events:[],animation:false,plugins:{visibleSharePercent:false,legend:{display:false},tooltip:{enabled:false}}}});
    modal.querySelectorAll('.distribution-track').forEach(el=>el.hidden=!valid);
  }
  function clear(){channelBrands.clear();selectedMetric='total';timelineMode='auto';drillRange=null;hiddenTimelineSeries.clear();collapse();render([]);}
  return{render,clear,compare,setChannels,brandLogo};
})();

'use strict';
window.DIYGraphs=(()=>{
  const host=document.getElementById('diyGraphs');
  host.innerHTML='<h2>DIY - Graphs</h2><div class="diy-controls"><label>Chart<select id="diyType"><option value="bar">Bar</option><option value="line">Line</option><option value="grouped">Double bar</option><option value="mixed">Bar + line</option><option value="pie">Pie</option></select></label><label>Group by<select id="diyGroup"><option value="day">Date</option><option value="channel">Channel</option></select></label><label>Metric<select id="diyFirst"></select></label><label id="diySecondLabel">Second metric<select id="diySecond"></select></label></div><div class="diy-presets"><label>Saved presets<select id="diySaved"><option value="">Choose preset</option></select></label><label>Preset name<input id="diyName" maxlength="80" autocomplete="off"></label><button id="diySave" type="button">Save preset</button><button id="diyDelete" type="button" disabled>Delete preset</button></div><p id="diyStatus" role="status"></p><div class="diy-frame"><canvas id="diyCanvas" role="img" aria-label="Custom graph"></canvas></div>';
  const names={views:'Views',impressions:'Ad impressions',ad:'Ad revenue',other:'Sponsorship / others',total:'Total revenue'},colors=['#5484a4','#fa6980','#09a1a1','#d396a6','#f6c992','#acc0d3'];
  const el=id=>document.getElementById(id);let rows=[],presets=[],chart=null,allRows=[],generation=0;
  const filters=document.createElement('div');filters.className='diy-controls';
  filters.innerHTML='<label>From<input id="diyStart" type="date"></label><label>To<input id="diyEnd" type="date"></label><button id="diyAllDates" type="button">All dates</button><details id="diyChannels"><summary>Channels</summary><div class="diy-channel-menu"><input id="diySearch" type="search" placeholder="Search channels" aria-label="Search DIY channels"><div><button id="diySelectAll" type="button">Select all</button><button id="diyClearChannels" type="button">Clear</button></div><div id="diyChannelOptions"></div></div></details>';
  host.querySelector('h2').after(filters);
  const datePickers=new Map();
  function availableDates(){const ids=selected();return new Set(allRows.filter(row=>ids.includes(row.channel_id)).map(row=>row.day));}
  function syncDates(){const dates=availableDates();for(const picker of datePickers.values()){picker.redraw();if(!picker.input.value&&dates.size)picker.jumpToDate([...dates].sort().at(-1));}}
  function setupDates(){if(!window.flatpickr)return;for(const id of ['diyStart','diyEnd']){if(datePickers.has(id))continue;const input=el(id);input.type='text';input.placeholder=id==='diyStart'?'From date':'To date';const picker=flatpickr(input,{dateFormat:'Y-m-d',disableMobile:true,monthSelectorType:'static',onReady:(_,__,instance)=>{instance.calendarContainer.classList.add('diy-calendar');},onOpen:(_,__,instance)=>{if(!input.value){const dates=[...availableDates()].sort();if(dates.length)instance.jumpToDate(dates.at(-1));}},onDayCreate:(_,__,instance,day)=>{const key=instance.formatDate(day.dateObj,'Y-m-d'),hasData=availableDates().has(key);day.classList.toggle('diy-date-data',hasData);day.title=hasData?'Data available':'No data';day.setAttribute('aria-label',day.getAttribute('aria-label')+(hasData?', data available':', no data'));},onChange:()=>applyFilters()});datePickers.set(id,picker);}}
  filters.addEventListener('focusin',setupDates);
  function selected(){return [...el('diyChannelOptions').querySelectorAll('input:checked')].map(input=>Number(input.value));}
  function applyFilters(){const {start,end}=normalizeDateInputs(el('diyStart'),el('diyEnd')),ids=selected();rows=allRows.filter(r=>(!start||r.day>=start)&&(!end||r.day<=end)&&ids.includes(r.channel_id));for(const [id,picker] of datePickers)picker.setDate(el(id).value,false);syncDates();render();}
  for(const id of ['diyStart','diyEnd','diyChannelOptions'])el(id).addEventListener('change',applyFilters);
  el('diyAllDates').onclick=()=>{el('diyStart').value='';el('diyEnd').value='';applyFilters();};
  el('diySearch').oninput=()=>{for(const label of el('diyChannelOptions').children)label.hidden=!label.textContent.toLowerCase().includes(el('diySearch').value.toLowerCase());};
  for(const [id,checked] of [['diySelectAll',true],['diyClearChannels',false]])el(id).onclick=()=>{for(const label of el('diyChannelOptions').children)if(!label.hidden)label.querySelector('input').checked=checked;applyFilters();};
  for(const id of ['diyFirst','diySecond'])for(const [key,name] of Object.entries(names)){const option=document.createElement('option');option.value=key;option.textContent=name;el(id).append(option);}
  el('diyFirst').value='ad';el('diySecond').value='other';
  el('diySecond').prepend(new Option('None','none'));
  const config=()=>({type:el('diyType').value,group:el('diyGroup').value,first:el('diyFirst').value,second:el('diySecond').value,start:el('diyStart').value,end:el('diyEnd').value,channels:selected()});
  const monetary=key=>['ad','other','total'].includes(key);
  el('diyGroup').append(new Option('Daily leader','leader'));
  let insightPresets=[];
  const details=document.createElement('div');details.className='diy-data';details.id='diyData';host.append(details);
  const dayLabel=day=>new Date(day+'T00:00:00Z').toLocaleDateString('en-GB',{day:'2-digit',month:'short',year:'numeric',timeZone:'UTC'});
  function detailTable(headers,records){
    details.replaceChildren();if(!records.length)return;
    const table=document.createElement('table'),thead=document.createElement('thead'),head=document.createElement('tr'),body=document.createElement('tbody');
    for(const name of headers){const th=document.createElement('th');th.scope='col';th.textContent=name;head.append(th);}thead.append(head);
    for(const record of records){const tr=document.createElement('tr');for(const value of record){const td=document.createElement('td');td.textContent=value;tr.append(td);}body.append(tr);}
    table.append(thead,body);details.append(table);
  }
  function presetOptions(){
    const examples=document.createElement('optgroup');examples.label='Insight presets';examples.append(...insightPresets.map(p=>new Option(p.name,p.id)));
    const personal=document.createElement('optgroup');personal.label='My saved presets';personal.append(...presets.map(p=>new Option(p.name,p.id)));
    el('diySaved').replaceChildren(new Option('Choose preset',''),examples,personal);
  }
  function calendarSeries(entries){
    if(!entries.length)return [];
    const map=new Map(entries),result=[],last=entries.at(-1)[0],date=new Date(entries[0][0]+'T00:00:00Z');
    while(date.toISOString().slice(0,10)<=last){const day=date.toISOString().slice(0,10);result.push([day,map.get(day)??null]);date.setUTCDate(date.getUTCDate()+1);}
    return result;
  }
  function dailyLeaders(metric){
    const days=new Map();for(const row of rows){if(!days.has(row.day))days.set(row.day,new Map());const channels=days.get(row.day);channels.set(row.channel,(channels.get(row.channel)||0)+row[metric]);}
    return [...days].sort(([a],[b])=>a.localeCompare(b)).map(([day,channels])=>{
      const entries=[...channels],max=Math.max(...entries.map(([,value])=>value)),winners=entries.filter(([,value])=>value===max).map(([name])=>name).sort();
      const sum=entries.reduce((total,[,value])=>total+value,0),nonnegative=entries.every(([,value])=>value>=0);
      return {day,value:max,winners,share:sum>0&&nonnegative?(max/sum*100).toFixed(1)+'%':'N/A',coverage:channels.size+'/'+selected().length};
    });
  }
  el('diyType').querySelector('[value="pie"]').textContent='Doughnut / share';
  const frame=host.querySelector('.diy-frame'),share=document.createElement('div');share.className='diy-share';share.hidden=true;
  const centre=document.createElement('div');centre.className='diy-share-centre';centre.hidden=true;frame.append(centre);
  const breakdown=document.createElement('div');breakdown.className='diy-share-breakdown';
  const expand=document.createElement('button');expand.type='button';expand.textContent='Show all';expand.setAttribute('aria-expanded','false');
  const list=document.createElement('div');list.className='diy-share-list';breakdown.append(expand,list);frame.after(share);share.append(frame,breakdown);
  let expanded=false;
  expand.onclick=()=>{expanded=!expanded;render();};
  const format=(value,key)=>new Intl.NumberFormat('en-IN',{maximumFractionDigits:0,...(monetary(key)?{style:'currency',currency:'INR'}:{})}).format(value/(monetary(key)?100:1));
  function renderShare(items,c){
    const ranked=[...items].sort((a,b)=>b[1][c.first]-a[1][c.first]);
    const total=ranked.reduce((sum,[,v])=>sum+v[c.first],0),negative=ranked.some(([,v])=>v[c.first]<0);
    const shown=expanded?ranked:ranked.slice(0,5);
    if(!expanded&&ranked.length>5)shown.push(['Others ('+(ranked.length-5)+')',{[c.first]:ranked.slice(5).reduce((sum,[,v])=>sum+v[c.first],0)}]);
    expand.hidden=ranked.length<=5;expand.textContent=expanded?'Show top 5':'Show all ('+ranked.length+')';expand.setAttribute('aria-expanded',String(expanded));
    list.replaceChildren();centre.replaceChildren();const value=document.createElement('strong'),label=document.createElement('span');value.textContent=format(total,c.first);label.textContent=names[c.first];centre.append(value,label);
    for(const [i,[name,values]] of shown.entries()){
      const row=document.createElement('div');row.className='diy-share-row';row.style.setProperty('--share-color',colors[i%colors.length]);
      const nameLabel=document.createElement('strong');nameLabel.textContent=name;
      const figures=document.createElement('span');const percent=total>0&&!negative?values[c.first]/total*100:0;
      figures.textContent=format(values[c.first],c.first)+' | '+(negative?'N/A':percent>0&&percent<0.1?'<0.1%':percent.toFixed(1)+'%');
      const track=document.createElement('div');track.className='diy-share-track';const bar=document.createElement('span');bar.style.width=percent+'%';track.append(bar);row.append(nameLabel,figures,track);list.append(row);
    }
    if(negative||!total){el('diyStatus').textContent=negative?'Negative values cannot form a doughnut. Values are listed below.':items.length?'No positive values for this metric.':'No data for the selected dates and channels.';return;}
    chart=new Chart(el('diyCanvas'),{type:'doughnut',data:{labels:shown.map(([name])=>name),datasets:[{data:shown.map(([,v])=>v[c.first]),backgroundColor:shown.map((_,i)=>colors[i%colors.length]),borderWidth:2,borderColor:'#fff',hoverOffset:0}]},options:{responsive:true,maintainAspectRatio:false,cutout:'76%',animation:false,plugins:{legend:{display:false},tooltip:{callbacks:{label:ctx=>format(ctx.raw,c.first)+' | '+(ctx.raw/total*100).toFixed(1)+'%'}}}}});
  }
  function render(values=rows){rows=values;const c=config(),dual=c.type!=='pie'&&c.group!=='leader'&&c.second!=='none';el('diySecondLabel').hidden=c.type==='pie'||c.group==='leader';
    if(chart){chart.destroy();chart=null;}if(host.hidden)return;
    details.replaceChildren();
    const isShare=c.type==='pie';share.hidden=!isShare;centre.hidden=!isShare;
    if(isShare)share.prepend(frame);else share.before(frame);
    frame.classList.toggle('diy-share-frame',isShare);
    if(c.group==='leader'){
      const leaders=calendarSeries(dailyLeaders(c.first).map(row=>[row.day,row])).map(([day,row])=>row||{day,value:null,winners:['No records'],share:'N/A',coverage:'0/'+selected().length});
      el('diyStatus').textContent=leaders.length?'':'No data for the selected dates and channels.';
      detailTable(['Date','Leading channel (ties included)',names[c.first],'Share per leader','Channels with records'],leaders.map(row=>[dayLabel(row.day),row.winners.join(', '),row.value===null?'N/A':format(row.value,c.first),row.share,row.coverage]));
      if(isShare){el('diyStatus').textContent='Daily leaders are separate daily results, not parts of one total. Choose Bar or Line.';centre.replaceChildren();list.replaceChildren();expand.hidden=true;return;}
      chart=new Chart(el('diyCanvas'),{type:c.type==='line'?'line':'bar',data:{labels:leaders.map(row=>row.day),datasets:[{label:names[c.first],data:leaders.map(row=>row.value===null?null:row.value/(monetary(c.first)?100:1)),backgroundColor:colors[0],borderColor:colors[0],borderWidth:2,maxBarThickness:48,spanGaps:false}]},options:{responsive:true,maintainAspectRatio:false,animation:false,scales:{x:{offset:c.type!=='line',ticks:{maxTicksLimit:8,maxRotation:30}},y:{beginAtZero:true,title:{display:true,text:names[c.first]+(monetary(c.first)?' (INR)':'')}}},plugins:{legend:{display:false},tooltip:{callbacks:{afterLabel:ctx=>{const row=leaders[ctx.dataIndex];return [row.winners.join(', '),'Share per leader: '+row.share,'Channels with records: '+row.coverage];}}}}}});
      return;
    }
    const groups=new Map();for(const r of rows){const key=c.group==='day'?r.day:r.channel;if(!groups.has(key))groups.set(key,{views:0,impressions:0,ad:0,other:0,total:0});for(const metric of Object.keys(names))groups.get(key)[metric]+=r[metric];}
    const items=[...groups].sort((a,b)=>c.group==='day'?a[0].localeCompare(b[0]):b[1][c.first]-a[1][c.first]);
    el('diyStatus').textContent=items.length?'':'No data for the selected dates and channels.';
    if(isShare){renderShare(items,c);return;}
    const keys=dual?[c.first,c.second]:[c.first];const separate=dual&&monetary(c.first)!==monetary(c.second);
    const relation=c.group==='day'&&keys.includes('views')&&keys.includes('total');
    const coverage=new Map();for(const row of rows){if(!coverage.has(row.day))coverage.set(row.day,new Set());coverage.get(row.day).add(row.channel_id);}
    const change=(current,previous)=>previous==null||previous<0?'N/A':previous===0?(current===0?'0%':'New'):(current>=previous?'+':'')+((current-previous)/previous*100).toFixed(1)+'%';
    detailTable([c.group==='day'?'Date':'Channel',...keys.map(key=>names[key]),...(relation?['Views change','Revenue change','Revenue / 1K views','Channels with records']:[])],items.map(([name,v])=>{
      const date=new Date(name+'T00:00:00Z');if(relation)date.setUTCDate(date.getUTCDate()-1);const previousDay=relation?date.toISOString().slice(0,10):null;
      const complete=relation&&coverage.get(name)?.size===selected().length&&coverage.get(previousDay)?.size===selected().length;
      const previous=complete?groups.get(previousDay):null;
      return [c.group==='day'?dayLabel(name):name,...keys.map(key=>format(v[key],key)),...(relation?[change(v.views,previous?.views),change(v.total,previous?.total),v.views>0?format(v.total/v.views*1000,'total'):'N/A',coverage.get(name).size+'/'+selected().length]:[])];
    }));
    const plotted=c.group==='day'?calendarSeries(items):items;
    const datasets=keys.map((key,i)=>({label:names[key],data:plotted.map(([,v])=>v===null?null:v[key]/(monetary(key)?100:1)),type:c.type==='line'||(c.type==='mixed'&&i===1)?'line':'bar',backgroundColor:colors[i],borderColor:colors[i],borderWidth:c.type==='line'||c.type==='mixed'?2:0,yAxisID:separate&&i===1?'right':'y',maxBarThickness:48,pointRadius:3,spanGaps:false}));
    const axis=key=>({beginAtZero:true,title:{display:true,text:names[key]+(monetary(key)?' (INR)':'')},grid:{color:'#e6edf1'}});
    const scales=c.type==='pie'?{}:{x:{offset:c.type!=='line',ticks:{autoSkip:true,maxTicksLimit:8,maxRotation:30}},y:axis(c.first)};
    if(separate)scales.right={...axis(c.second),position:'right',grid:{drawOnChartArea:false}};
    chart=new Chart(el('diyCanvas'),{type:c.type==='line'?'line':'bar',data:{labels:plotted.map(([name])=>name),datasets},options:{responsive:true,maintainAspectRatio:false,animation:false,interaction:{mode:'index',intersect:false},scales,plugins:{legend:{position:'bottom'},tooltip:{callbacks:{label:ctx=>{const key=keys[ctx.datasetIndex]||c.first;return names[key]+': '+new Intl.NumberFormat('en-IN',{maximumFractionDigits:0,...(monetary(key)?{style:'currency',currency:'INR'}:{})}).format(ctx.raw);}}}}}});
  }
  async function load(){const ticket=++generation;el('diyStatus').textContent='Loading...';const previous=selected(),initialized=el('diyChannelOptions').children.length>0;const response=await api('/api/graph-presets');const data=await api('/api/report');if(ticket!==generation)return;allRows=data.rows;presets=response.rows;insightPresets=response.examples||[];el('diyChannelOptions').replaceChildren();for(const channel of me.channels){const label=document.createElement('label'),input=document.createElement('input');input.type='checkbox';input.value=channel.id;input.checked=!initialized||previous.includes(channel.id);label.append(input,document.createTextNode(channel.name));el('diyChannelOptions').append(label);}el('diySearch').oninput();presetOptions();el('diyDelete').disabled=true;applyFilters();}
  for(const id of ['diyType','diyGroup','diyFirst','diySecond'])el(id).addEventListener('change',()=>render());
  el('diySaved').onchange=()=>{const personal=presets.find(p=>String(p.id)===el('diySaved').value),preset=personal||insightPresets.find(p=>p.id===el('diySaved').value);el('diyDelete').disabled=!personal;if(!preset)return;for(const [key,id] of Object.entries({type:'diyType',group:'diyGroup',first:'diyFirst',second:'diySecond'}))el(id).value=preset.config[key];if(personal){el('diyStart').value=preset.config.start||'';el('diyEnd').value=preset.config.end||'';for(const input of el('diyChannelOptions').querySelectorAll('input'))input.checked=!preset.config.channels||preset.config.channels.includes(Number(input.value));}el('diyName').value=preset.name;applyFilters();};
  el('diySave').onclick=async()=>{el('diySave').disabled=true;try{await api('/api/graph-presets',{method:'POST',body:{name:el('diyName').value,config:config()}});await load();el('diyStatus').textContent='Preset saved.';}catch(error){if(!error.stale)el('diyStatus').textContent=error.message;}finally{el('diySave').disabled=false;}};
  el('diyDelete').onclick=async()=>{const id=el('diySaved').value;if(!id||!confirm('Delete this graph preset?'))return;try{await api('/api/graph-presets/'+id,{method:'DELETE'});await load();}catch(error){if(!error.stale)el('diyStatus').textContent=error.message;}};
  function clear(){generation++;rows=[];allRows=[];presets=[];expanded=false;list.replaceChildren();centre.replaceChildren();details.replaceChildren();el('diyChannelOptions').replaceChildren();el('diyStart').value='';el('diyEnd').value='';if(chart){chart.destroy();chart=null;}el('diySaved').replaceChildren(new Option('Choose preset',''));el('diyName').value='';el('diyDelete').disabled=true;el('diyStatus').textContent='';}
  return{render,load,clear};
})();

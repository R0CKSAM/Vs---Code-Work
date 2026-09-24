'use strict';
window.QuickInsights=(()=>{
  const metrics={total:'Total revenue',ad:'Ad revenue',other:'Sponsorship / others',views:'Views',impressions:'Ad impressions'};
  const cash=n=>new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:0}).format(n/100);
  const rate=n=>new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',minimumFractionDigits:2,maximumFractionDigits:2}).format(n/100);
  const number=n=>new Intl.NumberFormat('en-IN',{maximumFractionDigits:0}).format(n);
  const pct=n=>Math.abs(n)<0.1&&n!==0?(n<0?'>-0.1':'<0.1'):n.toFixed(1);
  const total=rows=>rows.reduce((sum,row)=>{for(const key of Object.keys(metrics))sum[key]+=row[key];return sum;},{total:0,ad:0,other:0,views:0,impressions:0});
  function group(rows,key){const map=new Map();for(const row of rows){if(!map.has(row[key]))map.set(row[key],[]);map.get(row[key]).push(row);}return [...map].map(([name,values])=>({name,...total(values)}));}
  function build(data,requested,previous=null,status='pending'){
    const params=new URLSearchParams(requested),rows=data.rows||[],out=[],comparisonVisuals={};
    const add=(id,title,evidence,action,priority=20,kind='neutral')=>out.push({id,title,evidence,action,priority,kind});
    if(!rows.length)return out;
    const days=[...new Set(rows.map(row=>row.day))].sort(),start=params.get('start')||days[0],end=params.get('end')||days.at(-1);
    const channelIds=[...new Set(params.getAll('channel').filter(id=>id!=='none'))],channelCount=channelIds.length||new Set(rows.map(row=>row.channel_id)).size;
    const span=Math.round((Date.parse(end)-Date.parse(start))/86400000)+1;
    const coverage=new Set(rows.map(row=>row.day+'|'+row.channel_id)).size,expected=span*channelCount,complete=expected>0&&coverage===expected;
    const sums=total(rows),channels=group(rows,'channel'),daily=group(rows,'day');
    const nonnegative=rows.every(row=>row.total>=0&&row.ad>=0&&row.other>=0);
    const single=channelCount===1;
    if(!complete)add('coverage','Incomplete reporting',single?number(days.length)+' of '+span+' selected days have records.':number(coverage)+' of '+number(expected)+' expected daily channel records are available.','Check missing uploads before comparing performance.',100,'warning');
    if(!nonnegative)add('negative','Revenue adjustments present','One or more records contain negative revenue.','Reconcile adjustments before interpreting revenue shares.',99,'warning');
    let comparisonComplete=false;
    if(previous){
      const before=total(previous.rows),priorCoverage=new Set(previous.rows.map(row=>row.day+'|'+row.channel_id)).size;
      comparisonComplete=complete&&priorCoverage===expected;
      const priorEnd=new Date(Date.parse(start)-86400000).toISOString().slice(0,10),priorStart=new Date(Date.parse(start)-span*86400000).toISOString().slice(0,10);
      if(!comparisonComplete)add('comparison','Period comparison unavailable','Current: '+coverage+'/'+expected+' daily channel records. Previous ('+priorStart+' to '+priorEnd+'): '+priorCoverage+'/'+expected+'.','Missing records are not treated as zero. Period growth is withheld until reporting is complete.',90,'warning');
      else for(const [key,name] of Object.entries(metrics)){
        const now=sums[key],old=before[key],fmt=['views','impressions'].includes(key)?number:cash;
        if(old<0||now<0||(old===0&&now===0))continue;
        const delta=old>0?(now-old)/old*100:null;
        const state=delta===null?(now===0?'unchanged':'now recorded'):Math.abs(delta)<1?'broadly stable':delta>0?'increased':'decreased';
        add('change-'+key,name+' '+state,fmt(now)+' vs '+fmt(old)+(delta!==null?' ('+(delta>0?'+':'')+pct(delta)+'%)':'')+'; previous '+priorStart+' to '+priorEnd+'.',Math.abs(delta||0)>=1?(single?'Check this channel\'s daily trend and ad/sponsorship mix.':'Review channel-level contributions to this change.'):'Monitor the next comparable period.',key==='total'?88:50+(Math.min(Math.abs(delta||0),20)),delta!==null&&delta< -1?'warning':'neutral');
      }
      if(comparisonComplete&&nonnegative&&previous.rows.every(row=>row.total>=0&&row.ad>=0&&row.other>=0)&&sums.views>0&&before.views>0&&before.total>0){
        const now=sums.total/sums.views*1000,old=before.total/before.views*1000,delta=(now-old)/old*100;
        add('yield-change','Revenue per 1,000 views '+(Math.abs(delta)<1?'broadly stable':delta<0?'fell':'rose'),rate(now)+' vs '+rate(old)+' ('+(delta>0?'+':'')+pct(delta)+'%).','Review ad yield and sponsorship mix; this ratio alone does not establish a cause.',85,delta< -1?'warning':'neutral');
        comparisonVisuals['yield-change']={value:(delta>0?'+':'')+pct(delta)+'%',label:'Revenue / 1,000 views vs previous period'};
      }
      if(comparisonComplete&&channels.length>1){
        const oldChannels=new Map(group(previous.rows,'channel').map(row=>[row.name,row.total]));
        const movers=channels.map(row=>({...row,delta:row.total-(oldChannels.get(row.name)||0)})).sort((a,b)=>b.delta-a.delta||a.name.localeCompare(b.name));
        for(const [row,id,title] of [[movers[0],'gainer','Largest channel revenue gain'],[movers.at(-1),'decliner','Largest channel revenue decline']]){
          if(id==='gainer'?row.delta<=0:row.delta>=0)continue;
          const tied=movers.filter(item=>item.delta===row.delta);
          add(id,title+(tied.length>1?' (tied)':''),tied.map(item=>item.name+': '+cash(item.total)+' vs '+cash(oldChannels.get(item.name))).join('; ')+'. '+(row.delta>0?'+':'-')+cash(Math.abs(row.delta))+(tied.length>1?' each':'')+' versus the preceding period.','Review ad revenue and sponsorship changes separately.',82,row.delta<0?'warning':'neutral');
          comparisonVisuals[id]={value:(row.delta>0?'+':'-')+cash(Math.abs(row.delta)),label:'Revenue change vs previous period',impact:Math.abs(row.delta)};
        }
      }
    }else if(status==='unavailable')add('comparison','Comparison could not load','Current-period figures are available; prior-period data could not be fetched.','Retry before making a period-over-period decision.',90,'warning');
    const ranked=[...channels].sort((a,b)=>b.total-a.total||a.name.localeCompare(b.name));
    if(single)add('channel-summary',channels[0].name,cash(sums.total)+' total revenue from '+number(sums.views)+' views across '+days.length+' recorded day'+(days.length===1?'':'s')+'.',days.length>1?'Check peak days and revenue mix to understand this channel\'s results.':'This is a one-day snapshot; use a longer range to assess a trend.',78);
    if(!single&&complete&&ranked.length>1&&sums.total>0&&nonnegative){
      const leaders=ranked.filter(row=>row.total===ranked[0].total),leader=ranked[0];
      const runner=ranked.find(row=>row.total<leader.total);
      add('leader',leaders.length>1?'Revenue lead is tied':'Leading revenue channel',leaders.map(row=>row.name).join(', ')+': '+cash(leader.total)+(leaders.length>1?' each, ':', ')+pct(leader.total/sums.total*100)+'%'+(leaders.length>1?' each':'')+' of selected revenue.'+(runner?' Next: '+runner.name+' at '+cash(runner.total)+'; gap '+cash(leader.total-runner.total)+'.':' All selected channels are tied.'),'Review these channels alongside their view volume.',80);
      if(channelCount===2){const gap=ranked[0].total-ranked[1].total;
        if(gap>0)add('pair-gap','Revenue gap between selected channels',ranked[0].name+' earned '+cash(gap)+' more than '+ranked[1].name+'.','Compare view volume and revenue mix before judging relative efficiency.',79);
      }
      const share=leader.total/sums.total*100;
      if(share>=(channelCount===2?75:50))add('concentration','Revenue concentration',leader.name+' contributes '+pct(share)+'% of revenue within the '+channelCount+' selected channels.','Monitor dependence within this selection; this does not describe unselected channels.',84,'warning');
    }
    if(daily.length>1&&complete&&nonnegative&&sums.total>0){const peak=Math.max(...daily.map(row=>row.total)),winners=daily.filter(row=>row.total===peak);
      if(winners.length===daily.length)add('steady-days','Daily revenue unchanged',cash(peak)+' on each of '+daily.length+' days.','Check whether the steady total reflects recurring income or offsetting ad and sponsorship changes.',60);
      else {const average=sums.total/daily.length,delta=(peak-average)/average*100;add('peak',winners.length>1?'Highest revenue days (tied)':'Highest revenue day',winners.map(row=>row.name).join(', ')+': '+cash(peak)+(winners.length>1?' each.':'.')+' Range daily average: '+cash(average)+'; peak is '+pct(delta)+'% higher.',single?'Review this channel\'s ad and sponsorship entries on the peak date'+(winners.length>1?'s.':'.'):'Review which channels and revenue sources contributed on these dates.',76);comparisonVisuals.peak={value:'+'+pct(delta)+'%',label:'Above selected-range daily average'};}}
    if(nonnegative&&sums.total>0){
      add('mix','Revenue mix',cash(sums.ad)+' ads ('+pct(sums.ad/sums.total*100)+'%); '+cash(sums.other)+' sponsorship / others ('+pct(sums.other/sums.total*100)+'%).',sums.other>sums.ad?'Check whether sponsorship income is recurring or one-off.':'Review ad performance separately from sponsorship activity.',45);
      if(sums.views>0)add('yield','Revenue per 1,000 views',cash(sums.total/sums.views*1000)+' across '+number(sums.views)+' views.','Compare this with a complete prior period; total revenue includes sponsorship.',40);
    }
    if(sums.views>0&&sums.impressions>=0)add('exposure','Ad impressions relative to views',pct(sums.impressions/sums.views*100)+' ad impressions per 100 views.','Review ad delivery separately; this is not a fill rate or unique-viewer conversion rate.',30);
    if(sums.impressions>0&&sums.ad>=0)add('ad-yield','Ad revenue per 1,000 impressions',cash(sums.ad/sums.impressions*1000)+' across '+number(sums.impressions)+' recorded ad impressions.','Compare ad yield for similar inventory and reporting periods.',35);
    const noRevenue=channels.filter(row=>row.views>0&&row.total===0);
    if(noRevenue.length&&sums.total!==0)add('unmonetized','Views with zero net revenue',noRevenue.map(row=>row.name).join(', ')+': '+number(noRevenue.reduce((n,row)=>n+row.views,0))+' views and zero net revenue.','Check reporting, monetization eligibility and adjustments before assuming missed earnings.',75,'warning');
    if(sums.total===0)add('zero','No net revenue recorded',cash(sums.total)+' across '+number(sums.views)+' views.','Verify reporting and any offsetting adjustments.',85,'warning');
    const visuals={
      coverage:{value:number(coverage)+' / '+number(expected),label:'Daily channel records',bar:coverage/expected*100},
      comparison:{value:'Not comparable',label:'Previous period'},
      negative:{value:'Adjustment review',label:'Negative revenue entries'},
      'channel-summary':{value:cash(sums.total),label:'Total revenue'},
      leader:{value:cash(ranked[0]?.total||0),label:'Leading channel revenue'},
      concentration:{value:pct((ranked[0]?.total||0)/sums.total*100)+'%',label:'Largest channel share',bar:(ranked[0]?.total||0)/sums.total*100},
      'pair-gap':{value:cash((ranked[0]?.total||0)-(ranked[1]?.total||0)),label:'Revenue gap'},
      peak:{value:cash(Math.max(...daily.map(row=>row.total))),label:'Peak daily revenue'},
      'steady-days':{value:cash(daily[0]?.total||0),label:'Revenue each day'},
      mix:{value:pct(sums.ad/sums.total*100)+'% ads',label:cash(sums.other)+' sponsorship / others',bar:sums.ad/sums.total*100},
      yield:{value:cash(sums.total/sums.views*1000),label:'Revenue / 1,000 views'},
      'ad-yield':{value:cash(sums.ad/sums.impressions*1000),label:'Ad revenue / 1,000 impressions'},
      exposure:{value:pct(sums.impressions/sums.views*100),label:'Ad impressions / 100 views'},
      zero:{value:cash(0),label:'Net revenue'},
      unmonetized:{value:number(noRevenue.reduce((n,row)=>n+row.views,0)),label:'Views with zero net revenue'}
    };
    if(previous){const before=total(previous.rows);for(const key of Object.keys(metrics)){const old=before[key],now=sums[key];visuals['change-'+key]={value:old>0?((now-old)>0?'+':'')+pct((now-old)/old*100)+'%':now>0?'New':'Unchanged',label:metrics[key]};}visuals['yield-change']={value:cash(sums.views>0?sums.total/sums.views*1000:0),label:'Current revenue / 1,000 views'};}
    const before=previous?total(previous.rows):null;
    const oldChannels=new Map(previous?group(previous.rows,'channel').map(row=>[row.name,row.total]):[]);
    function presentation(item){
      const result={title:item.title,icon:item.kind==='warning'?'triangle-alert':'chart-no-axes-combined',value:(comparisonVisuals[item.id]||visuals[item.id]).value,context:(comparisonVisuals[item.id]||visuals[item.id]).label,tone:item.kind==='warning'?'caution':'neutral'};
      const pair=(current,baseline,formatter,labels=['Current','Previous'])=>[{name:labels[0],value:current,text:formatter(current)},{name:labels[1],value:baseline,text:formatter(baseline)}];
      const comparison=(current,baseline)=>{const change=baseline>0?(current-baseline)/baseline*100:null;result.badge=change===null?'New':(change>0?'+':'')+pct(change)+'%';result.badgeLabel='vs previous '+span+' day'+(span===1?'':'s');result.tone=change!==null&&Math.abs(change)<1?'neutral':current<baseline?'down':'up';};
      if(item.id.startsWith('change-')){const key=item.id.slice(7),formatter=['views','impressions'].includes(key)?number:cash;result.title=metrics[key];result.icon={total:'indian-rupee',ad:'megaphone',other:'handshake',views:'eye',impressions:'mouse-pointer-click'}[key];result.value=formatter(sums[key]);result.context='Selected '+span+'-day period';result.pairs=pair(sums[key],before[key],formatter);comparison(sums[key],before[key]);}
      else if(item.id==='yield-change'){const current=sums.total/sums.views*1000,baseline=before.total/before.views*1000;result.title='Earnings per 1,000 views';result.icon='eye';result.value=rate(current);result.context='Includes ads and sponsorship / others';result.pairs=pair(current,baseline,rate);comparison(current,baseline);}
      else if(['gainer','decliner'].includes(item.id)){const ordered=channels.map(row=>({...row,delta:row.total-oldChannels.get(row.name)})).sort((a,b)=>b.delta-a.delta);const winner=item.id==='gainer'?ordered[0]:ordered.at(-1),ties=ordered.filter(row=>row.delta===winner.delta);result.title=item.id==='gainer'?'Largest channel gain':'Largest channel decline';result.icon=item.id==='gainer'?'trending-up':'trending-down';result.tone=item.id==='gainer'?'up':'down';result.context=(item.id==='gainer'?'More':'Less')+' revenue vs previous '+span+' days'+(ties.length>1?' (each)':'');result.channel=ties.map(row=>row.name).join(', ');if(ties.length===1)result.pairs=pair(winner.total,oldChannels.get(winner.name),cash);}
      else if(item.id==='leader'){const leaders=ranked.filter(row=>row.total===ranked[0].total),runner=ranked.find(row=>row.total<ranked[0].total);result.title=leaders.length>1?'Highest-earning channels (tied)':'Highest-earning channel';result.icon='trophy';result.channel=leaders.map(row=>row.name).join(', ');result.context=leaders.length>1?'Revenue per tied channel':'Selected-period revenue';result.badge=pct(ranked[0].total/sums.total*100)+'%';result.badgeLabel=leaders.length>1?'each of selected revenue':'of selected revenue';if(runner&&leaders.length===1)result.pairs=pair(ranked[0].total,runner.total,cash,['#1','#2']);}
      else if(item.id==='peak'){const maximum=Math.max(...daily.map(row=>row.total)),average=sums.total/daily.length;result.title='Highest-earning day';result.icon='calendar-days';result.tone='peak';result.value=cash(maximum);result.context='Selected-period daily revenue';result.channel=daily.filter(row=>row.total===maximum).map(row=>row.name).join(', ');result.badge='+'+pct((maximum-average)/average*100)+'%';result.badgeLabel='above the range\'s daily average';result.series=[...daily].sort((a,b)=>a.name.localeCompare(b.name)).map(row=>({name:row.name,value:row.total}));}
      return result;
    }
    return out.map(item=>({...item,kpi:presentation(item),visual:comparisonVisuals[item.id]||visuals[item.id],impact:comparisonVisuals[item.id]?.impact||0})).sort((a,b)=>b.priority-a.priority||b.impact-a.impact||a.id.localeCompare(b.id));
  }
  function curate(items){
    const ids=new Set(items.map(item=>item.id));
    const filtered=items.filter(item=>item.id!=='comparison'&&!(item.id==='leader'&&(ids.has('concentration')||ids.has('pair-gap')))&&!(item.id==='yield'&&ids.has('yield-change')));
    const important=filtered.filter(item=>item.priority>=75);
    for(const item of filtered)if(important.length<4&&!important.includes(item))important.push(item);
    return important.sort((a,b)=>b.priority-a.priority||(b.impact||0)-(a.impact||0)||a.id.localeCompare(b.id));
  }
  let section,list,scope,note,insights=[],stripInsight=null,lastStripId=null;
  function paintStrip(){
    const strip=document.getElementById('performanceInsight');if(!strip)return;
    strip.hidden=!stripInsight;
    const text=strip.querySelector('p');text.replaceChildren();
    if(!stripInsight){delete strip.dataset.insight;return;}
    strip.dataset.insight=stripInsight.id;
    const title=document.createElement('strong');title.textContent=stripInsight.title+'. ';
    text.append(title,document.createTextNode(stripInsight.evidence+' '+stripInsight.action));
  }
  function selectStrip(status){
    if(status==='pending'){stripInsight=null;paintStrip();return;}
    const pool=curate(insights).filter(item=>item.id!=='comparison');
    const alternatives=pool.filter(item=>item.id!==lastStripId),eligible=alternatives.length?alternatives:pool;
    stripInsight=eligible.length?eligible[Math.floor(Math.random()*eligible.length)]:null;
    if(stripInsight)lastStripId=stripInsight.id;
    paintStrip();
  }
  function mount(){if(section)return;
    section=document.createElement('section');section.id='quickInsights';section.setAttribute('aria-labelledby','quickInsightsTitle');
    section.innerHTML='<div class="insights-heading"><div><h2 id="quickInsightsTitle">Quick Insights</h2><p id="insightScope"></p></div></div><p id="insightNote" role="status"></p><div id="insightList"></div>';
    document.getElementById('insightsView').append(section);
    list=section.querySelector('#insightList');scope=section.querySelector('#insightScope');note=section.querySelector('#insightNote');
  }
  function paint(){
    list.replaceChildren();
    const node=(tag,className,text)=>{const element=document.createElement(tag);element.className=className;if(text!==undefined)element.textContent=text;return element;};
    for(const item of curate(insights)){const kpi=item.kpi,article=node('article','insight-item kpi-'+kpi.tone);article.dataset.insight=item.id;article.dataset.priority=item.priority;
      const heading=node('div','kpi-heading'),icon=node('span','kpi-icon'),glyph=node('i','');glyph.dataset.lucide=kpi.icon;glyph.setAttribute('aria-hidden','true');icon.append(glyph);heading.append(icon,node('h3','',kpi.title));
      article.append(heading,node('strong','insight-value',kpi.value),node('span','insight-value-label',kpi.context));
      if(kpi.channel)article.append(node('p','kpi-channel',kpi.channel));
      if(kpi.badge){const change=node('div','kpi-change');change.append(node('strong','kpi-badge',kpi.badge),node('span','',kpi.badgeLabel));article.append(change);}
      if(kpi.pairs){const comparison=node('div','kpi-comparison'),maximum=Math.max(...kpi.pairs.map(row=>Math.abs(row.value)));
        for(const [i,row] of kpi.pairs.entries()){const line=node('div','kpi-pair'+(i?' baseline':'')),track=node('div','kpi-track'),fill=node('span','');track.setAttribute('aria-hidden','true');if(row.value>=0)fill.style.width=(maximum?row.value/maximum*100:0)+'%';track.append(fill);line.append(node('span','',row.name),track,node('strong','',row.text));comparison.append(line);}article.append(comparison);
      }else if(kpi.series){const chart=node('div','kpi-daily'),maximum=Math.max(...kpi.series.map(row=>row.value));chart.setAttribute('role','img');chart.setAttribute('aria-label',kpi.series.map(row=>row.name+': '+cash(row.value)).join('; '));for(const row of kpi.series){const bar=node('span',row.value===maximum?'peak':'');bar.style.height=(maximum?row.value/maximum*100:0)+'%';bar.title=row.name+': '+cash(row.value);chart.append(bar);}article.append(chart);const dates=node('div','kpi-dates');dates.append(node('span','',kpi.series[0].name),node('span','',kpi.series.at(-1).name));article.append(dates);
      }else if(Number.isFinite(item.visual.bar)){const track=node('div','insight-bar'),fill=node('span','');track.setAttribute('aria-hidden','true');fill.style.width=Math.max(0,Math.min(100,item.visual.bar))+'%';track.append(fill);article.append(track);}
      article.append(node('p','insight-evidence',item.evidence),node('p','insight-action',item.action));list.append(article);}
    window.lucide?.createIcons();
  }
  function render(data,requested,previous=null,status='pending'){
    mount();
    const params=new URLSearchParams(requested),count=params.getAll('channel').filter(id=>id!=='none').length;
    const channelNames=[...new Set(data.rows.map(row=>row.channel))];
    const first=params.get('start'),last=params.get('end'),date=value=>new Date(value+'T00:00:00Z').toLocaleDateString('en-GB',{day:'2-digit',month:'short',year:'numeric',timeZone:'UTC'});
    scope.textContent=(first&&last?(first===last?date(first):date(first)+' - '+date(last)):'All available dates')+' | '+count+' selected channel'+(count===1?'':'s')+(count>0&&count<=2&&channelNames.length?' | '+channelNames.join(' + '):'');
    insights=build(data,requested,previous,status);note.textContent=!data.rows.length?'No data for this selection.':status==='pending'?'Comparing with the preceding period...':'';section.removeAttribute('aria-busy');paint();
    selectStrip(status);
  }
  function clear(message=''){insights=[];stripInsight=null;paintStrip();if(!section)return;scope.textContent='';note.textContent=message;list.replaceChildren();}
  return {build,curate,render,clear,paintStrip};
})();

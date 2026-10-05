(function(root){
  'use strict';
  const DAY=86400000,keys=['ad','other','views','impressions'];
  const iso=value=>new Date(value).toISOString().slice(0,10);
  const stamp=value=>Date.parse(value+'T00:00:00Z');
  function aggregate(rows,{start,end,mode='auto',channelCount=0}={}){
    const dates=rows.map(row=>row.day).sort();
    let first=start||dates[0],last=end||dates.at(-1);
    if(!first||!last)return {interval:'day',buckets:[],start:first,end:last};
    if(first>last)[first,last]=[last,first];
    const from=stamp(first),to=stamp(last);
    if(!Number.isFinite(from)||!Number.isFinite(to))return {interval:'day',buckets:[]};
    const span=Math.round((to-from)/DAY)+1;
    const interval=mode==='auto'?(span<=31?'day':span<=120?'week':'month'):mode;
    if(!['day','week','month'].includes(interval))throw new Error('Unknown timeline interval');
    const buckets=[],byDate=new Map();
    const channels=channelCount||new Set(rows.map(row=>row.channel_id??row.channel)).size;
    for(let cursor=from;cursor<=to;){
      const date=new Date(cursor);
      const naturalStart=interval==='month'?Date.UTC(date.getUTCFullYear(),date.getUTCMonth(),1):interval==='week'?cursor-((date.getUTCDay()+6)%7)*DAY:cursor;
      const naturalEnd=interval==='month'?Date.UTC(date.getUTCFullYear(),date.getUTCMonth()+1,1)-DAY:interval==='week'?naturalStart+6*DAY:cursor;
      const finish=Math.min(to,naturalEnd),bucket={start:iso(cursor),end:iso(finish),periodStart:iso(naturalStart),partial:cursor!==naturalStart||finish!==naturalEnd,values:Object.fromEntries(keys.map(key=>[key,0])),records:new Set(),days:new Set(),daily:new Map()};
      bucket.expectedRecords=(Math.round((finish-cursor)/DAY)+1)*channels;
      for(let day=cursor;day<=finish;day+=DAY)byDate.set(iso(day),bucket);
      buckets.push(bucket);cursor=finish+DAY;
    }
    for(const row of rows){
      const bucket=byDate.get(row.day);if(!bucket)continue;
      bucket.days.add(row.day);bucket.records.add(row.day+'|'+(row.channel_id??row.channel));
      if(!bucket.daily.has(row.day))bucket.daily.set(row.day,{ad:0,other:0,views:0,impressions:0});
      for(const key of keys){bucket.values[key]+=row[key];bucket.daily.get(row.day)[key]+=row[key];}
    }
    return {interval,start:first,end:last,buckets:buckets.map(bucket=>({
      ...bucket,reportedDays:bucket.days.size,reportedRecords:bucket.records.size,
      missing:bucket.records.size===0,incomplete:bucket.records.size<bucket.expectedRecords,
      values:bucket.records.size?bucket.values:Object.fromEntries(keys.map(key=>[key,null])),
      daily:[...bucket.daily].map(([day,values])=>({day,...values})),days:undefined,records:undefined
    }))};
  }
  const api={aggregate};
  if(typeof module==='object'&&module.exports)module.exports=api;else root.RevenueTimelineData=api;
})(globalThis);

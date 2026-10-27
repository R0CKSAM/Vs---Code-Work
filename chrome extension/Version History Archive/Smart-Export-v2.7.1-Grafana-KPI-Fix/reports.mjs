/* Smart Export v2: documented, fixed analytics templates. No arbitrary SQL or network URL input. */
import {assertDateRange,buildGeoSql,istMidnightMs,addDays,validYMD} from './core.mjs';
export const REPORT_ORDER=['kpis','channel','geo','devices','content','traffic'];
export const REPORTS={
  executive:{title:'Executive Workbook',short:'Six reports in one Excel workbook',sourceIds:[2,1,8,6,7,12,5,41,49,11,15,34,68,20,58,55,27,9,38]},
  kpis:{title:'Daily KPIs',short:'Users, sessions, views, watch time and bandwidth',sourceIds:[2,1,8,6,7,12,5,41,49,11,15],dimension:['date'],metrics:['unique_devices','session_ids','unique_ips','new_users','returning_users','ip_ua_sessions','manifest_views','session_hours','avg_watch_minutes_per_user','playtime_minutes','bandwidth_bytes']},
  channel:{title:'Channel Performance',short:'Daily channel playtime and unique IPs',sourceIds:[34,68],dimension:['date','channel_name'],metrics:['playtime_minutes','unique_ips']},
  geo:{title:'GEO Performance',short:'Daily playtime by country, state and city',sourceIds:[20],dimension:['date','country','state','city'],metrics:['playtime_minutes']},
  devices:{title:'Device & OS',short:'Daily platform/OS combinations and distinct counts',sourceIds:[58,55],dimension:['date','platform','operating_system'],metrics:['unique_devices','unique_ips']},
  content:{title:'Popular Content',short:'Daily title-level views, users and sessions',sourceIds:[27],dimension:['date','content_title'],metrics:['manifest_views','unique_ips','unique_devices','session_ids']},
  traffic:{title:'Traffic Trends',short:'Hourly IST trends, views, IPs and bandwidth',sourceIds:[9,38,3,15],dimension:['date','hour_ist'],metrics:['unique_ips','session_ids','manifest_views','playtime_minutes','bandwidth_bytes']}
};
export const REPORT_COLUMNS={
  kpis:[['date','Date (IST)'],['unique_devices','Unique device IDs'],['session_ids','Distinct session IDs'],['unique_ips','Unique IPs'],['new_users','New users (single session in day)'],['returning_users','Returning users (multiple sessions in day)'],['ip_ua_sessions','IP + UA sessions'],['manifest_views','Manifest requests (views proxy)'],['session_hours','Session duration (hours)'],['avg_watch_minutes_per_user','Avg watch time per IP (min)'],['playtime_minutes','Estimated playtime (min)'],['bandwidth_bytes','Video bandwidth (bytes)']],
  channel:[['date','Date (IST)'],['channel_name','Channel'],['playtime_minutes','Estimated playtime (min)'],['unique_ips','Unique IPs']],
  geo:[['date','Date (IST)'],['country','Country'],['state','State'],['city','City'],['playtime_minutes','Estimated playtime (min)']],
  devices:[['date','Date (IST)'],['platform','Device platform'],['operating_system','Operating system'],['unique_devices','Distinct device IDs'],['unique_ips','Unique IPs']],
  content:[['date','Date (IST)'],['content_title','Content title (raw from URL)'],['manifest_views','Matching manifest requests'],['unique_ips','Unique IPs'],['unique_devices','Distinct device IDs'],['session_ids','Distinct session IDs']],
  traffic:[['date','Date (IST)'],['hour_ist','Hour (IST)'],['unique_ips','Unique IPs'],['session_ids','Distinct session IDs'],['manifest_views','Manifest requests (views proxy)'],['playtime_minutes','Estimated playtime (min)'],['bandwidth_bytes','Video bandwidth (bytes)']]
};
export const EXCEL_SHEETS={kpis:'Daily KPIs',channel:'Channel Performance',geo:'GEO Performance',devices:'Device and OS',content:'Popular Content',traffic:'Traffic Trends'};
export const DEFINITIONS=[
 ['Estimated playtime (minutes)','Count of matching 6-second TS segment requests multiplied by 6/60. Proxy; not measured player time.'],
 ['Manifest views','Count of master-manifest requests matching the original Grafana definition. Not unique video starts.'],
 ['Distinct device IDs','Distinct device_id values in each individual daily report group; not confirmed unique people.'],
 ['Unique IPs','Distinct client IP addresses; multiple people may share an IP and one person can use multiple IPs.'],
 ['Session IDs','Distinct session_id values; client instrumentation determines their reliability.'],
 ['New users','Count of device IDs with exactly one distinct session ID within each report day, matching the source Grafana new-user definition scoped to that day; not true first-time registrations.'],
 ['Returning users','Count of device IDs with more than one distinct session ID within each report day; not a cross-period return-cohort metric.'],
 ['Total Session Duration (Hours)','Estimated duration from matching six-second TS segments divided by 3600, following Grafana Panel 41.'],
 ['Avg Watch Time per user (Unique IP)','Estimated minutes from matching six-second TS segments with a channel name, divided by unique IPs in that matching traffic; zero if no matching IPs.'],
 ['Total Unique IPs & Session','Grafana Panel 11 contains two existing measures: unique_cliIP and unique_session (unique IP+UA). The checkbox selects these two export columns together; it is not a third, additive measure.'],
 ['IP + User Agent sessions','Distinct IP-and-user-agent pairs; a proxy for sessions, not session IDs.'],
 ['Bandwidth (bytes)','Sum of successful matching .ts request bytes, consistent with the source panel.'],
 ['Daily counts','Distinct counts must NOT be summed across dates/groups to produce monthly unique users. Run a separate period-level distinct query.'],
 ['Channel unique IPs','Counts matching channel_name traffic broadly; playtime only uses validated TS segment requests.'],
 ['Device & OS','Platform and OS are classified from UA using CASE statements from the source dashboard, then grouped together.'],
 ['Content title','Raw content_title value extracted from the queryStr field of matching .m3u8 requests.'],
 ['Time zone','Date and hour grouping uses Asia/Kolkata. Only completed IST dates are queried.'],
 ['Filters','Grafana ad hoc filter variables must be empty in both saved URL and open Grafana tab; filtered exports are blocked.'],
 ['Source','TrafficPeak Grafana / Veto_Streamin.logs / Hydrolix queries; requires signed-in Chrome tab.']
];
const SEGMENT="reqPath LIKE '%.ts' AND reqPath NOT LIKE '%.m3u8' AND statusCode IN (200, 206) AND extract(reqPath, '[-_](\\\\d+)\\\\.ts$') != ''";
const VIDEO_BYTES="reqPath LIKE '%.ts' AND statusCode IN (200, 206)";
const MASTER="(URL like '%main.m3u8%' OR URL like '%satsangmaster.m3u8%' OR URL like '%sanskarmaster.m3u8%' OR URL like '%index.m3u8%' OR URL like '%shubhmaster.m3u8%' OR URL like '%playlist.m3u8%' OR URL like '%master.m3u8%')";
const D="toDate(toTimeZone(reqTimeSec, 'Asia/Kolkata'))";
// Classifications below are populated from the approved dashboard's original Panel 58 and Panel 55.
const PLATFORM_CASE=String.raw`CASE
        WHEN UA LIKE '%AFT%' THEN 'Amazon Fire TV'
        WHEN UA LIKE '%BRAVIA%' THEN 'Sony BRAVIA'
        WHEN UA LIKE '%MiTV%' OR UA LIKE '%MIBOX%' OR UA LIKE '%R3G%' OR UA LIKE '%R4G%' OR UA LIKE '%R4 Build%' THEN 'Xiaomi Mi TV'
        WHEN UA LIKE '%HiSmartTV%' OR UA LIKE '%hi352%' THEN 'Hisense Smart TV'
        WHEN UA LIKE '%PANASONIC%' THEN 'Panasonic TV'
        WHEN UA LIKE '%VU TV%' OR UA LIKE '%VU 4K%' THEN 'VU TV'
        WHEN UA LIKE '%Toshiba%' THEN 'Toshiba TV'
        WHEN UA LIKE '%Sharp%' OR UA LIKE '%SW-%' OR UA LIKE '%SWTV%' THEN 'Sharp TV'
        WHEN UA LIKE '%Y Series%' THEN 'TCL TV'
        WHEN UA LIKE '%UnionTV%' THEN 'Union TV'
        WHEN UA LIKE '%Web0S%' OR UA LIKE '%WebAppManager%' THEN 'LG Smart TV'
        WHEN UA LIKE '%Apple TV%' THEN 'Apple TV'
        WHEN UA LIKE '%iPhone%' OR UA LIKE '%iPad%'  THEN 'iPhone/iPad'
        WHEN UA LIKE '%Tizen%' THEN 'Samsung Smart TV'
        WHEN UA LIKE '%Haier MatrixTV%' THEN 'Haier MatrixTV'
        WHEN UA LIKE '%Stream TV%' THEN 'Stream TV'
        WHEN UA LIKE '%Tata Sky Binge%' THEN 'Tata Sky Binge'
        WHEN UA LIKE '%NSTV%' THEN 'NSTV'
        WHEN UA LIKE '%SANSUI TV%' THEN 'SANSUI TV'
        WHEN UA LIKE '%AI PONT%' THEN 'AI PONT TV'
        WHEN UA LIKE '%BeyondTV%' THEN 'Beyond TV'
        WHEN UA LIKE '%XStream-Smart-Box%' THEN 'Airtel XStream Box'
        WHEN UA LIKE '%ExoPlayer%' THEN 'ExoPlayer-Android'
        ELSE 'Others'
    END`;
const OS_CASE=String.raw`CASE
        WHEN UA LIKE '%Web0S%' OR UA LIKE '%WebOS%'                        THEN 'webOS'
        WHEN UA LIKE '%Apple TV%'                                           THEN 'Apple TV'
        WHEN UA LIKE '%iPhone%' OR UA LIKE '%iPad%' 
             OR UA LIKE '%CPU OS%like Mac OS X%'                            THEN 'iOS'
        WHEN UA LIKE '%Macintosh%' OR UA LIKE '%Mac OS X%'                  THEN 'macOS'
        WHEN (UA LIKE '%Android%' OR UA LIKE '%Dalvik%') 
             AND UA LIKE '%AFT%'                                            THEN 'FireOS'
        WHEN (UA LIKE '%Android%' OR UA LIKE '%Dalvik%') 
             AND UA NOT LIKE '%AFT%'                                        THEN 'Android'
        ELSE 'Others'
    END`;
export function sqlForReport(report,from,to){
  if(report==='geo')return buildGeoSql(from,to);
  if(!REPORT_ORDER.includes(report))throw new Error('Unknown report template.');
  assertDateRange(from,to);
  const lo=Math.floor(istMidnightMs(from)/1000),hi=Math.floor(istMidnightMs(addDays(to,1))/1000);
  const range=`reqTimeSec >= toDateTime(${lo}, 'UTC') AND reqTimeSec < toDateTime(${hi}, 'UTC')`;
  const prefix='FROM Veto_Streamin.logs';
  const setting='SETTINGS hdx_query_max_execution_time=60';
  switch(report){
    case 'kpis': return `WITH
      device_session_counts AS (
        SELECT ${D} AS report_date, device_id, uniq(session_id) AS sessions_for_device
        ${prefix} WHERE ${range}
        GROUP BY report_date, device_id
      ),
      classified_users AS (
        SELECT report_date,
          countIf(sessions_for_device = 1) AS new_users,
          countIf(sessions_for_device > 1) AS returning_users
        FROM device_session_counts GROUP BY report_date
      ),
      daily_metrics AS (
        SELECT ${D} AS report_date,
          uniq(device_id) AS unique_devices,
          uniq(session_id) AS session_ids,
          uniqExact(cliIP) AS unique_ips,
          uniq(cliIP, UA) AS ip_ua_sessions,
          countIf(${MASTER}) AS manifest_views,
          round(countIf(${SEGMENT}) * 6.0 / 3600.0,2) AS session_hours,
          if(uniqIf(cliIP, (${SEGMENT}) AND channel_name != '') = 0, 0,
            round(countIf((${SEGMENT}) AND channel_name != '') * 6.0 / 60.0 /
              nullIf(uniqIf(cliIP, (${SEGMENT}) AND channel_name != ''),0),2)) AS avg_watch_minutes_per_user,
          round(countIf(${SEGMENT}) * 6.0 / 60.0,2) AS playtime_minutes,
          sumIf(bytes, ${VIDEO_BYTES}) AS bandwidth_bytes
        ${prefix} WHERE ${range} GROUP BY report_date
      )
      SELECT d.report_date, d.unique_devices, d.session_ids, d.unique_ips,
        ifNull(c.new_users,0) AS new_users,
        ifNull(c.returning_users,0) AS returning_users,
        d.ip_ua_sessions, d.manifest_views, d.session_hours,
        d.avg_watch_minutes_per_user, d.playtime_minutes, d.bandwidth_bytes
      FROM daily_metrics AS d LEFT JOIN classified_users AS c USING (report_date)
      ORDER BY report_date ${setting}`;
    case 'channel':return `SELECT ${D} AS report_date, channel_name, round(countIf(${SEGMENT}) * 6.0 / 60.0,2) AS playtime_minutes, uniqExact(cliIP) AS unique_ips ${prefix} WHERE ${range} AND channel_name != '' GROUP BY report_date, channel_name ORDER BY report_date, playtime_minutes DESC ${setting}`;
    case 'devices':return `SELECT ${D} AS report_date, ${PLATFORM_CASE} AS platform, ${OS_CASE} AS operating_system, uniq(device_id) AS unique_devices, uniqExact(cliIP) AS unique_ips ${prefix} WHERE ${range} GROUP BY report_date, platform, operating_system ORDER BY report_date, unique_devices DESC ${setting}`;
    case 'content':return `SELECT ${D} AS report_date, extract(queryStr, 'content_title=([^&]+)') AS content_title, count() AS manifest_views, uniqExact(cliIP) AS unique_ips, uniq(device_id) AS unique_devices, uniq(session_id) AS session_ids ${prefix} WHERE ${range} AND reqPath LIKE '%.m3u8' AND statusCode IN (200, 206) AND channel_name != '' AND content_title != '' GROUP BY report_date, content_title ORDER BY report_date, manifest_views DESC ${setting}`;
    case 'traffic':return `SELECT ${D} AS report_date, formatDateTime(toTimeZone(reqTimeSec,'Asia/Kolkata'), '%Y-%m-%d %H:00') AS hour_ist, uniqExact(cliIP) AS unique_ips, uniq(session_id) AS session_ids, countIf(${MASTER}) AS manifest_views, round(countIf(${SEGMENT}) * 6.0 / 60.0,2) AS playtime_minutes, sumIf(bytes, ${VIDEO_BYTES}) AS bandwidth_bytes ${prefix} WHERE ${range} GROUP BY report_date, hour_ist ORDER BY hour_ist ${setting}`;
  }
}
export function expectedSourcePanels(report){
  if(report==='executive')return [...new Set(REPORT_ORDER.flatMap(r=>REPORTS[r].sourceIds))];
  return REPORTS[report]?.sourceIds||[];
}
export function assertSourcePanels(report,panels){
  const ids=new Map(panels.map(p=>[Number(p.id),p]));
  for(const id of expectedSourcePanels(report))if(!ids.get(id)?.targets?.[0]?.rawSql)throw new Error(`Grafana dashboard source panel ${id} is missing or changed. Export halted.`);
  // Critical metric definitions must match the source. Identity of aggregate SQL alone is insufficient.
  if(report==='executive'||report==='geo'){
    const s=ids.get(20)?.targets?.[0]?.rawSql||'';
    if(!s.includes('count() * 6 / 60.0') || !s.includes('decodeURLComponent(country)'))throw new Error('GEO source panel definition changed. Review before exporting.');
  }
  if(report==='executive'||report==='kpis'){
    const views=ids.get(5)?.targets?.[0]?.rawSql||'';
    if(!views.includes('${master_manifest}')||!views.includes('count()'))throw new Error('Views source definition changed.');
    const newcomers=ids.get(6)?.targets?.[0]?.rawSql||'',returners=ids.get(7)?.targets?.[0]?.rawSql||'';
    if(!newcomers.includes('countIf(count_unique = 1)')||!returners.includes('countIf(count_unique > 1)'))throw new Error('Grafana new/returning user classification changed.');
    const avg=ids.get(49)?.targets?.[0]?.rawSql||'',table=ids.get(11)?.targets?.[0]?.rawSql||'';
    if(!avg.includes('uniq(cliIP)')||!avg.includes("channel_name != ''")||!table.includes('uniq(cliIP, UA)'))throw new Error('Grafana average-watch-time or IP/session table definition changed.');
  }
  if(report==='executive'||report==='content'){
    const s=ids.get(27)?.targets?.[0]?.rawSql||'';
    if(!s.includes('content_title=([^&]+)')||!s.includes('%.m3u8'))throw new Error('Content source definition changed.');
  }
  if(report==='executive'||report==='devices'){
    const p=ids.get(58)?.targets?.[0]?.rawSql||'',os=ids.get(55)?.targets?.[0]?.rawSql||'';
    if(!p.includes("THEN 'Amazon Fire TV'")||!os.includes("THEN 'webOS'"))throw new Error('Device platform or operating-system classification has changed.');
  }
  if(report==='executive'||report==='channel'){
    const p=ids.get(34)?.targets?.[0]?.rawSql||'',ips=ids.get(68)?.targets?.[0]?.rawSql||'';
    if(!p.includes('channel_name')||!p.includes('count() * 6 / 60.0')||!ips.includes('uniq(cliIP)'))throw new Error('Channel playtime or IP metric definition has changed.');
  }
  if(report==='executive'||report==='kpis'){
    const duration=ids.get(41)?.targets?.[0]?.rawSql||'',bytes=ids.get(15)?.targets?.[0]?.rawSql||'';
    if(!duration.includes('count() * 6 / 3600.0')||!bytes.includes('SUM(bytes)'))throw new Error('Playtime or bandwidth source definition has changed.');
  }
  return true;
}
function parseDate(value){
  if(typeof value==='number'){
    if(value>=19000101&&value<=21001231)return String(Math.trunc(value));
    // Some Grafana plugins serialize a SQL Date as days since the Unix epoch.
    if(Number.isInteger(value)&&value>=10000&&value<=60000)return new Date(value*86400000).toISOString().slice(0,10);
    const ms=value<1e11?value*1000:value;
    const d=new Date(ms);if(!Number.isFinite(d.getTime()))throw new Error('Invalid date timestamp in Grafana response.');
    return d.toISOString().slice(0,10);
  }
  return String(value??'').slice(0,10);
}
export function parseReportFrames(payload,report,from,to,diagnostics={}){
  if(!REPORT_ORDER.includes(report))throw new Error('Invalid report type.');
  const result=payload?.results?.A;
  if(!result)throw new Error(`Grafana returned no result for ${report}.`);
  if(result.error||Number(result.status)>=400)throw new Error(`Grafana ${report} error: ${result.error||result.message||result.status}`);
  if(!Array.isArray(result.frames))throw new Error(`Grafana ${report} response has no frames.`);
  const dims=REPORTS[report].dimension,nums=REPORTS[report].metrics;
  const rows=[],seen=new Map();
  diagnostics.duplicatesSkipped=0; diagnostics.frameCount=result.frames.length;
  for(const f of result.frames){
    const names=f?.schema?.fields?.map(x=>String(x.name||'').toLowerCase())||[];
    const values=f?.data?.values||[];if(!names.length)continue;
    const at=Object.fromEntries(names.map((n,i)=>[n,i]));
    const dateCol=at.report_date;
    if(dateCol===undefined)throw new Error(`Missing report_date in ${report}.`);
    for(const key of [...dims.filter(x=>x!=='date'),...nums])if(at[key]===undefined)throw new Error(`Missing expected ${report} column ${key}.`);
    const len=values[dateCol]?.length||0;
    if(names.some((_,i)=>(values[i]?.length||0)!==len))throw new Error('Inconsistent Grafana frame column lengths.');
    for(let i=0;i<len;i++){
      const obj={date:parseDate(values[dateCol][i])};
      if(!validYMD(obj.date)||obj.date<from||obj.date>to)throw new Error(`Invalid/out-of-range IST date for ${report}: ${obj.date}`);
      for(const d of dims){if(d==='date')continue;const v=String(values[at[d]][i]??'').trim();if(v.length>2000)throw new Error('Unexpectedly long Grafana dimension value.');obj[d]=v;}
      if(report==='traffic' && !/^\d{4}-\d{2}-\d{2} \d{2}:00$/.test(obj.hour_ist))throw new Error('Invalid IST hour bucket.');
      for(const n of nums){const raw=values[at[n]][i];if(raw===null||raw===undefined||raw==='')throw new Error(`Missing ${n} value from Grafana.`);const v=typeof raw==='number'?raw:Number(String(raw).replace(/,/g,''));if(!Number.isFinite(v)||v<0||v>Number.MAX_SAFE_INTEGER)throw new Error(`Invalid ${n} metric from Grafana.`);obj[n]=v;}
      const key=JSON.stringify(dims.map(x=>obj[x]));
      const previous=seen.get(key);
      if(previous){
        // The datasource may return several Grafana frames for one query. Repeated,
        // byte-for-byte equivalent groups are harmless retransmissions: collapse them.
        // Never SUM or arbitrarily overwrite conflicting values, especially uniq counts.
        const different=nums.filter(n=>previous[n]!==obj[n]);
        if(different.length){
          const group=dims.map(d=>`${d}=${String(obj[d]??'').slice(0,65)}`).join(', ');
          throw new Error(`Conflicting ${report} data for ${group}: ${different.join(', ')} differed between Grafana frames. Nothing was saved. Try a shorter range; contact Smarth if it persists.`);
        }
        diagnostics.duplicatesSkipped++;
        continue;
      }
      seen.set(key,obj);rows.push(obj);
    }
  }
  if(rows.length>80000)throw new Error(`${report} returned more than 80,000 rows; choose a smaller range.`);
  return rows;
}
export function datasetsFor(report){return report==='executive'?REPORT_ORDER:[report];}
export function rowsToCsv(report,rows){
  if(!REPORT_ORDER.includes(report))throw new Error('Choose one report for CSV.');
  const columns=REPORT_COLUMNS[report];
  const esc=(v)=>{let s=String(v??'');if(/^[\s]*[=+@\-\t\r]/.test(s))s="'"+s;return '"'+s.replace(/"/g,'""')+'"';};
  const out=[columns.map(c=>c[1]),...rows.map(r=>columns.map(c=>r[c[0]]))];
  return '\uFEFF'+out.map(row=>row.map(esc).join(',')).join('\r\n')+'\r\n';
}

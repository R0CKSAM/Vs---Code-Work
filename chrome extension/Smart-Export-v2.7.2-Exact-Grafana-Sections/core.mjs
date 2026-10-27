/* Smart Export: pure helpers; no browser permissions or private credentials. */
export const SOURCE_ORIGIN = 'https://grafana-apj.trafficpeak.live';
export const DASHBOARD_UID = 'db7ce6f6-d689-4976-89e5-ddf0b5401f97';
export const PANEL_NAME = 'Playtime by GEO';
export const FALLBACK_DATASOURCE_UID = 'ef79dxhbpxrswd';
export const DEFAULT_DASHBOARD_URL = `${SOURCE_ORIGIN}/d/${DASHBOARD_UID}/sessions-users-monitoring?orgId=743&from=now-7d&to=now&timezone=Asia%2FKolkata&var-filter=`;
export const DEFAULT_CONFIG = {
  dashboardUrl: DEFAULT_DASHBOARD_URL,
  orgId: '743',
  enabled: false,
  lastSuccessAt: null,
  lastDateFrom: null,
  lastDateTo: null,
  scheduleHourIST: 8,
  autoRefreshDays: 3,
  version: 1
};

function validYMD(s) {
  if (typeof s !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(s)) return false;
  const [y,m,d] = s.split('-').map(Number);
  const dt = new Date(Date.UTC(y,m-1,d));
  return dt.getUTCFullYear()===y && dt.getUTCMonth()+1===m && dt.getUTCDate()===d;
}
export { validYMD };
export function addDays(ymd, n) {
  if (!validYMD(ymd)) throw new Error('Invalid calendar date.');
  const [y,m,d] = ymd.split('-').map(Number);
  return new Date(Date.UTC(y,m-1,d+n)).toISOString().slice(0,10);
}
export function istToday(now = new Date()) {
  return new Date(now.getTime() + 330*60_000).toISOString().slice(0, 10);
}
export function istHour(now = new Date()) {
  return new Date(now.getTime()+330*60_000).getUTCHours();
}
export function istMidnightMs(ymd) {
  if (!validYMD(ymd)) throw new Error('Invalid IST date.');
  return Date.parse(ymd+'T00:00:00Z') - 330*60_000;
}
export function datesForLastCompleteDays(n = 7, now = new Date()) {
  const yesterday=addDays(istToday(now),-1);
  return {from:addDays(yesterday,1-n),to:yesterday};
}
export function assertDateRange(from, to, now = new Date()) {
  if (!validYMD(from) || !validYMD(to)) throw new Error('Choose valid start and end dates (YYYY-MM-DD).');
  if (from > to) throw new Error('The start date must be on or before the end date.');
  if (to >= istToday(now)) throw new Error('Export only completed IST dates. Choose yesterday or earlier.');
  const count=(istMidnightMs(to)-istMidnightMs(from))/86400000+1;
  if (count > 366) throw new Error('Maximum 366 days per sync; use smaller ranges for larger exports.');
  return count;
}
export function parseDashboardUrl(raw) {
  let u;
  try {u=new URL(raw)} catch {throw new Error('Enter a valid Grafana dashboard URL.');}
  if (u.origin!==SOURCE_ORIGIN) throw new Error('For safety, Smart Export only works with the configured TrafficPeak Grafana host.');
  const m=u.pathname.match(/^\/d\/([^/]+)(?:\/|$)/);
  if (!m || m[1] !== DASHBOARD_UID) throw new Error('Open the configured Sessions & Users dashboard; the dashboard UID does not match.');
  const orgId=u.searchParams.get('orgId')||'743';
  if (!/^\d{1,8}$/.test(orgId)) throw new Error('Invalid Grafana organization ID.');
  const vars=[];
  for (const [k,v] of u.searchParams.entries()) {
    if (k.startsWith('var-') && k!=='var-hdx_query_errors' && v.trim()) vars.push(`${k}=${v}`);
  }
  if (vars.length) throw new Error('Grafana dashboard filters are active. v1 cannot safely reproduce ad-hoc filters in the API query. Clear them before syncing: '+vars.join('; '));
  return {origin:u.origin, uid:m[1], orgId, datasetKey:`${u.origin}|${m[1]}|org=${orgId}|filters=none`, url:u.toString()};
}
export function buildGeoSql(from, to) {
  assertDateRange(from,to);
  const fromSec=Math.floor(istMidnightMs(from)/1000);
  const untilSec=Math.floor(istMidnightMs(addDays(to,1))/1000);
  // Matches original Playtime by GEO panel filters and 6-second video-segment proxy.
  // Avoids macro interpolation by pinning the source table from the supplied dashboard export.
  return `SELECT
  toDate(toTimeZone(reqTimeSec, 'Asia/Kolkata')) AS report_date,
  decodeURLComponent(country) AS country,
  decodeURLComponent(state) AS state,
  decodeURLComponent(city) AS city,
  round(count() * 6.0 / 60.0, 2) AS playtime_minutes
FROM Veto_Streamin.logs
WHERE reqTimeSec >= toDateTime(${fromSec}, 'UTC')
  AND reqTimeSec < toDateTime(${untilSec}, 'UTC')
  AND reqPath LIKE '%.ts'
  AND statusCode IN (200, 206)
  AND state != ''
  AND extract(reqPath, '[-_](\\\\d+)\\\\.ts$') != ''
GROUP BY report_date, country, state, city
ORDER BY report_date ASC, playtime_minutes DESC
SETTINGS hdx_query_max_execution_time=60`;
}
const norm = x => String(x??'').trim();
export function parseGrafanaFrames(payload, from, to, diagnostics={}) {
  if (payload?.error) throw new Error(String(payload.error));
  const result=payload?.results?.A;
  if (!result) throw new Error('Grafana returned no result A. Check the datasource and Grafana permissions.');
  if (result.error || result.status>=400) throw new Error(result.error || result.message || `Grafana returned status ${result.status}`);
  if (!Array.isArray(result.frames)) throw new Error('Unexpected response: missing data frames.');
  const output=[]; diagnostics.duplicatesSkipped=0; diagnostics.frameCount=result.frames.length;
  for (const frame of result.frames) {
    const fields=frame.schema?.fields||[];
    const values=frame.data?.values||[];
    if (!fields.length) continue;
    const col={}; fields.forEach((f,i)=>{col[String(f.name||'').toLowerCase()]=i;});
    const get=(aliases,j)=>{
      const i=aliases.map(x=>col[x]).find(x=>Number.isInteger(x));
      return i===undefined?undefined:values[i]?.[j];
    };
    if (!('report_date' in col) || !('playtime_minutes' in col)) throw new Error('Query returned unexpected columns; refusing to merge data.');
    const len=values[col.report_date]?.length||0;
    for (let j=0;j<len;j++) {
      let date=get(['report_date'],j);
      if (typeof date==='number') date=new Date(date<1e11?date*1000:date).toISOString().slice(0,10);
      date=norm(date).slice(0,10);
      if (!validYMD(date) || date<from || date>to) throw new Error('Grafana returned a date outside the requested IST range: '+date);
      const country=norm(get(['country'],j));
      const state=norm(get(['state'],j));
      const city=norm(get(['city'],j));
      const raw=get(['playtime_minutes'],j);
      if(raw===null||raw===undefined||typeof raw==='string'&&raw.trim()==='')throw new Error('Missing playtime value returned by Grafana.');
      const value=typeof raw==='number'?raw:Number(String(raw??'').replace(/,/g,''));
      if (!Number.isFinite(value) || value<0) throw new Error('Invalid playtime value returned by Grafana.');
      output.push({date,country,state,city,playtime_minutes:Math.round(value*100)/100});
    }
  }
  // Repeated Grafana frames may echo identical grouped rows. Keep one exact row;
  // do not merge conflicting playtime values (which could hide a broken query).
  const keys=new Map(),unique=[];
  for(const r of output){
    const key=JSON.stringify([r.date,r.country,r.state,r.city]);
    if(keys.has(key)){
      if(keys.get(key)!==r.playtime_minutes)throw new Error(`Conflicting GEO playtime for ${r.date} / ${r.country} / ${r.state} / ${r.city}. Nothing was saved; contact Smarth if it persists.`);
      diagnostics.duplicatesSkipped++;
      continue;
    }
    keys.set(key,r.playtime_minutes);unique.push(r);
  }
  return unique;
}
export function normalizeRows(rows) {
  return [...rows].sort((a,b)=>a.date.localeCompare(b.date)||a.country.localeCompare(b.country)||a.state.localeCompare(b.state)||a.city.localeCompare(b.city));
}
function safeCsvCell(value) {
  let s=String(value??'');
  // CSV exported from external data should not execute formulas on opening in Excel.
  if (/^\s*[=+@\-\t\r]/.test(s)) s="'"+s;
  return '"'+s.replace(/"/g,'""')+'"';
}
export function toCSV(rows) {
  const hdr=['Date (IST)','Country','State','City','Playtime (minutes)'];
  const body=normalizeRows(rows).map(r=>[r.date,r.country,r.state,r.city,r.playtime_minutes]);
  return '\ufeff'+[hdr,...body].map(row=>row.map(safeCsvCell).join(',')).join('\r\n')+'\r\n';
}
export function summarize(rows) {
  const dates=new Set(rows.map(x=>x.date));
  return {rows:rows.length,days:dates.size,from:rows.length?[...dates].sort()[0]:null,to:rows.length?[...dates].sort().at(-1):null};
}
export function dailyTotals(rows) {
  const sums=new Map();
  const counts=new Map();
  for(const r of rows){sums.set(r.date,(sums.get(r.date)||0)+r.playtime_minutes);counts.set(r.date,(counts.get(r.date)||0)+1);}
  const result=[...sums].sort((a,b)=>a[0].localeCompare(b[0]));
  return result.map(([date,total],i)=>({date,total_minutes:Math.round(total*100)/100,location_count:counts.get(date)}));
}

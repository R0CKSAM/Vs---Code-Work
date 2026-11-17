from pathlib import Path
exec((Path(__file__).resolve().parent/'analyze_source.py').read_text(encoding='utf-8-sig').split("d={}")[0])
r={
'daily_active':q('SELECT ist_date date_label,count(distinct ip) ips,sum(raw_ts_requests) requests FROM s WHERE raw_ts_requests>0 GROUP BY 1 ORDER BY 1'),
'active_repeat':q('WITH x AS (SELECT ip,count(distinct ist_date) nd,count(distinct "Event Name") ne FROM s WHERE raw_ts_requests>0 GROUP BY 1) SELECT count(*) ips,count(*) filter(where nd>1) repeat_ips,count(*) filter(where ne>1) cross_ips FROM x'),
'country_active':q("SELECT count(distinct country) countries,count(distinct country) filter(where country<>'IN' and country<>'') outside_india FROM s WHERE raw_ts_requests>0"),
'positive_matches':q('SELECT "Event Name" event_label,"Match Name" match_label,count(distinct ip) ips,sum(raw_ts_requests) requests FROM s WHERE raw_ts_requests>0 GROUP BY 1,2 ORDER BY ips DESC'),
}
(out/'active_metrics.json').write_text(json.dumps(r,indent=2));print(json.dumps(r,indent=2))

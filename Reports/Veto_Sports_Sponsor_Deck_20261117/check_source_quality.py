from pathlib import Path
exec((Path(__file__).resolve().parent/'analyze_source.py').read_text(encoding='utf-8-sig').split("d={}")[0])
queries={
'identity_quality':"SELECT count(*) filter(where lower(coalesce(dev,'')) in ('unknown','null','none','nan','-','0','na','n/a')) sentinel_rows,count(distinct ip) filter(where raw_ts_requests>0) positive_ips,count(distinct dev) filter(where raw_ts_requests>0) positive_devs,count(*) filter(where raw_ts_requests>0 and dev is null) positive_without_device,count(*) filter(where raw_ts_requests is null) null_requests FROM s",
'positive_identity_forms':"SELECT CASE WHEN dev IS NULL THEN 'blank' WHEN lower(dev) IN ('unknown','null','none','nan','-','0','na','n/a') THEN 'placeholder:'||dev ELSE 'nonempty' END kind,count(*) n FROM s WHERE raw_ts_requests>0 GROUP BY 1",
'country_reqs':"SELECT country category,sum(raw_ts_requests) requests,count(distinct ip) ips FROM s GROUP BY 1 ORDER BY requests DESC LIMIT 12",
'state_reqs':"SELECT state category,sum(raw_ts_requests) requests,count(distinct ip) ips FROM s WHERE country='IN' GROUP BY 1 ORDER BY requests DESC LIMIT 10",
'hosts': 'SELECT "Event Name" event_label,ReqHost host,count(*) n FROM s GROUP BY 1,2 ORDER BY n DESC',
'ip_engagement':"WITH x AS (SELECT ip,count(distinct ist_date) nd,count(distinct \"Event Name\") ne FROM s GROUP BY 1) SELECT count(*) ips,count(*) filter(where nd>1) repeat_ips,count(*) filter(where ne>1) cross_ips FROM x",
'ip_event_positive': 'SELECT "Event Name" event_label,count(distinct ip) filter(where raw_ts_requests>0) active_ips FROM s GROUP BY 1',
}
r={k:q(v) for k,v in queries.items()};(out/'quality_details.json').write_text(json.dumps(r,indent=2,default=str));print(json.dumps(r,indent=2))

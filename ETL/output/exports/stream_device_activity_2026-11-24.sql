-- Query 1: top 10 UA-decoded device labels. Place the cursor here and press Ctrl+Enter.
WITH stream_day_requests AS (
SELECT nullif(trim(cliIP), '') AS cli_ip,
       lower(trim(reqHost)) AS host,
       UA AS raw_ua,
       split_part(reqPath, '?', 1) AS path,
       queryStr,
       TRY_CAST(reqTimeSec AS DOUBLE) AS req_epoch,
       reqPath LIKE '%.ts' AS is_ts
FROM read_parquet(
    'Z:/Veto Logs Backup/DO NOT DELETE/source=stream/year=2026/month=11/day=24/part_*.parquet',
    hive_partitioning = false
)
),
stream_ua_lookup AS (
SELECT ua_norm,
       coalesce(CASE WHEN lower(trim(brand)) NOT IN ('', 'unknown', 'unknown / na', 'na', 'n/a') THEN trim(brand) END, CASE WHEN lower(trim(api_brand)) NOT IN ('', 'unknown', 'unknown / na', 'na', 'n/a') THEN trim(api_brand) END) AS brand,
       coalesce(CASE WHEN lower(trim(model)) NOT IN ('', 'unknown', 'unknown / na', 'na', 'n/a') THEN trim(model) END, CASE WHEN lower(trim(api_model)) NOT IN ('', 'unknown', 'unknown / na', 'na', 'n/a') THEN trim(api_model) END) AS model,
       coalesce(CASE WHEN lower(trim(device_type)) NOT IN ('', 'unknown', 'unknown / na', 'na', 'n/a') THEN trim(device_type) END, CASE WHEN lower(trim(api_device_type)) NOT IN ('', 'unknown', 'unknown / na', 'na', 'n/a') THEN trim(api_device_type) END) AS device_type,
       concat_ws(' ', coalesce(CASE WHEN lower(trim(os_name)) NOT IN ('', 'unknown', 'unknown / na', 'na', 'n/a') THEN trim(os_name) END, CASE WHEN lower(trim(api_os_name)) NOT IN ('', 'unknown', 'unknown / na', 'na', 'n/a') THEN trim(api_os_name) END),
                      coalesce(CASE WHEN lower(trim(os_version)) NOT IN ('', 'unknown', 'unknown / na', 'na', 'n/a') THEN trim(os_version) END, CASE WHEN lower(trim(api_os_version)) NOT IN ('', 'unknown', 'unknown / na', 'na', 'n/a') THEN trim(api_os_version) END)) AS os
FROM read_parquet('D:/Veto Logs Backup/Vs - Code Work/ETL/output/device_decode/ua_decode_lookup_both_all.parquet')
WHERE ua_norm IS NOT NULL
QUALIFY row_number() OVER (PARTITION BY ua_norm ORDER BY decoded_at_utc DESC NULLS LAST) = 1
),
pairs AS (
    SELECT cli_ip, raw_ua, count(*) AS segment_requests
    FROM stream_day_requests
    WHERE is_ts AND cli_ip IS NOT NULL AND raw_ua IS NOT NULL
    GROUP BY cli_ip, raw_ua
)
SELECT coalesce(brand, 'Unknown') AS brand, model,
       count(*) AS unique_ip_ua_pairs, sum(segment_requests) AS segment_requests
FROM pairs p JOIN stream_ua_lookup u ON u.ua_norm = NULLIF(trim(regexp_replace(regexp_replace(COALESCE(try(url_decode(COALESCE(try(url_decode(COALESCE(try(url_decode(COALESCE(try(url_decode(COALESCE(try(url_decode(CAST(p.raw_ua AS VARCHAR))), CAST(p.raw_ua AS VARCHAR)))), COALESCE(try(url_decode(CAST(p.raw_ua AS VARCHAR))), CAST(p.raw_ua AS VARCHAR))))), COALESCE(try(url_decode(COALESCE(try(url_decode(CAST(p.raw_ua AS VARCHAR))), CAST(p.raw_ua AS VARCHAR)))), COALESCE(try(url_decode(CAST(p.raw_ua AS VARCHAR))), CAST(p.raw_ua AS VARCHAR)))))), COALESCE(try(url_decode(COALESCE(try(url_decode(COALESCE(try(url_decode(CAST(p.raw_ua AS VARCHAR))), CAST(p.raw_ua AS VARCHAR)))), COALESCE(try(url_decode(CAST(p.raw_ua AS VARCHAR))), CAST(p.raw_ua AS VARCHAR))))), COALESCE(try(url_decode(COALESCE(try(url_decode(CAST(p.raw_ua AS VARCHAR))), CAST(p.raw_ua AS VARCHAR)))), COALESCE(try(url_decode(CAST(p.raw_ua AS VARCHAR))), CAST(p.raw_ua AS VARCHAR))))))), COALESCE(try(url_decode(COALESCE(try(url_decode(COALESCE(try(url_decode(COALESCE(try(url_decode(CAST(p.raw_ua AS VARCHAR))), CAST(p.raw_ua AS VARCHAR)))), COALESCE(try(url_decode(CAST(p.raw_ua AS VARCHAR))), CAST(p.raw_ua AS VARCHAR))))), COALESCE(try(url_decode(COALESCE(try(url_decode(CAST(p.raw_ua AS VARCHAR))), CAST(p.raw_ua AS VARCHAR)))), COALESCE(try(url_decode(CAST(p.raw_ua AS VARCHAR))), CAST(p.raw_ua AS VARCHAR)))))), COALESCE(try(url_decode(COALESCE(try(url_decode(COALESCE(try(url_decode(CAST(p.raw_ua AS VARCHAR))), CAST(p.raw_ua AS VARCHAR)))), COALESCE(try(url_decode(CAST(p.raw_ua AS VARCHAR))), CAST(p.raw_ua AS VARCHAR))))), COALESCE(try(url_decode(COALESCE(try(url_decode(CAST(p.raw_ua AS VARCHAR))), CAST(p.raw_ua AS VARCHAR)))), COALESCE(try(url_decode(CAST(p.raw_ua AS VARCHAR))), CAST(p.raw_ua AS VARCHAR)))))), '\+', ' ', 'g'), '\s+', ' ', 'g')), '')
WHERE model IS NOT NULL
GROUP BY 1, 2
ORDER BY unique_ip_ua_pairs DESC, segment_requests DESC, brand, model
LIMIT 10;

-- Query 2: press Ctrl+Enter for a sample. Replace NULL in settings with a quoted IP to inspect it.
WITH settings AS (
    SELECT NULL::VARCHAR AS target_ip
),
stream_day_requests AS (
SELECT nullif(trim(cliIP), '') AS cli_ip,
       lower(trim(reqHost)) AS host,
       UA AS raw_ua,
       split_part(reqPath, '?', 1) AS path,
       queryStr,
       TRY_CAST(reqTimeSec AS DOUBLE) AS req_epoch,
       reqPath LIKE '%.ts' AS is_ts
FROM read_parquet(
    'Z:/Veto Logs Backup/DO NOT DELETE/source=stream/year=2026/month=11/day=24/part_*.parquet',
    hive_partitioning = false
)
),
stream_ua_lookup AS (
SELECT ua_norm,
       coalesce(CASE WHEN lower(trim(brand)) NOT IN ('', 'unknown', 'unknown / na', 'na', 'n/a') THEN trim(brand) END, CASE WHEN lower(trim(api_brand)) NOT IN ('', 'unknown', 'unknown / na', 'na', 'n/a') THEN trim(api_brand) END) AS brand,
       coalesce(CASE WHEN lower(trim(model)) NOT IN ('', 'unknown', 'unknown / na', 'na', 'n/a') THEN trim(model) END, CASE WHEN lower(trim(api_model)) NOT IN ('', 'unknown', 'unknown / na', 'na', 'n/a') THEN trim(api_model) END) AS model,
       coalesce(CASE WHEN lower(trim(device_type)) NOT IN ('', 'unknown', 'unknown / na', 'na', 'n/a') THEN trim(device_type) END, CASE WHEN lower(trim(api_device_type)) NOT IN ('', 'unknown', 'unknown / na', 'na', 'n/a') THEN trim(api_device_type) END) AS device_type,
       concat_ws(' ', coalesce(CASE WHEN lower(trim(os_name)) NOT IN ('', 'unknown', 'unknown / na', 'na', 'n/a') THEN trim(os_name) END, CASE WHEN lower(trim(api_os_name)) NOT IN ('', 'unknown', 'unknown / na', 'na', 'n/a') THEN trim(api_os_name) END),
                      coalesce(CASE WHEN lower(trim(os_version)) NOT IN ('', 'unknown', 'unknown / na', 'na', 'n/a') THEN trim(os_version) END, CASE WHEN lower(trim(api_os_version)) NOT IN ('', 'unknown', 'unknown / na', 'na', 'n/a') THEN trim(api_os_version) END)) AS os
FROM read_parquet('D:/Veto Logs Backup/Vs - Code Work/ETL/output/device_decode/ua_decode_lookup_both_all.parquet')
WHERE ua_norm IS NOT NULL
QUALIFY row_number() OVER (PARTITION BY ua_norm ORDER BY decoded_at_utc DESC NULLS LAST) = 1
),
stream_host_map AS (
SELECT * FROM (VALUES
    ('veto-vod.akamaized.net', 'Veto VOD'),
    ('ndtvprofit-veto.akamaized.net', 'NDTV Profit'),
    ('ndtvprofit-veto.akamaized-staging.net', 'NDTV Profit'),
    ('manorama-veto.akamaized.net', 'Manorama'),
    ('b4u-veto-m.akamaized.net', 'B4U Movies'),
    ('b4u-veto-music.akamaized.net', 'B4U Music'),
    ('b4u-veto-kadak.akamaized.net', 'B4U Kadak'),
    ('b4u-veto.akamaized.net', 'B4U Bhojpuri'),
    ('vetocricket.akamaized.net', 'Veto Cricket Live'),
    ('bmasala-live.akamaized.net', 'Bollywood Masala')
) AS mappings(host, channel)
),
stream_path_map AS (
SELECT * FROM (VALUES
    ('f98c8ae68a354ab59a4e28e3dd700d4f', 'Davis Cup (f98c8)'),
    ('3b9668eaa10546528bc10dc0fbaf23bd', 'Davis Cup (3b966)'),
    ('bf34b69777604be0bc28ef9cb0136175', 'Davis Cup (bf34b)'),
    ('d1ff5a8a65014ff9b5bac219e1cf7d52', 'Davis Cup (d1ff5)'),
    ('a9b4ff0235174bab8c5ddae2123bff72', 'Davis Cup (a9b4f)'),
    ('834dd92ceaae4da3b254facc10ef79cf', 'Davis Cup (834dd)'),
    ('vglive-sk-238731', 'NDTV Marathi'),
    ('vglive-sk-639201', 'IndiaTV Cricket'),
    ('vglive-sk-834057', 'Ndtv India'),
    ('vglive-sk-274906', 'India TV'),
    ('vglive-sk-385006', 'India TV Yoga'),
    ('vglive-sk-479089', 'India TV SpeedNews'),
    ('vglive-sk-912213', 'India TV Adalat'),
    ('vglive-sk-699286', 'India TV Yoga'),
    ('vglive-sk-494434', 'NDTV Rajasthan'),
    ('vglive-sk-618504', 'NDTV Madhya Pradesh'),
    ('vglive-sk-722277', 'NDTV 24x7'),
    ('speednews', 'India TV SpeedNews'),
    ('rimo', 'India TV SpeedNews'),
    ('yrfmusic', 'YRF Music'),
    ('sagamusic', 'SAGA Music'),
    ('sikhratnavali', 'Sikh Ratnavali'),
    ('sagaharyanvi', 'Saga Music Haryanvi'),
    ('epic_tv', 'Epic TV'),
    ('epic_bharat', 'Epic Bharat'),
    ('epic_bhojpuri', 'Epic Bhojpuri'),
    ('epic_kids', 'Epic Kids'),
    ('epic_music', 'Epic Music'),
    ('national', 'NewsNation'),
    ('nnup', 'NewsNation UP/UK'),
    ('nnmp', 'NewsNation MP/CH'),
    ('nnbrjh', 'NewsNation BR/JH'),
    ('nnpunj', 'NewsNation Punjab'),
    ('sanskar', 'Sanskaar TV'),
    ('sanskaartv', 'Sanskaar TV'),
    ('satsang', 'Satsangh TV'),
    ('satsanghtv', 'Satsangh TV'),
    ('shubh', 'Shubh TV'),
    ('shubhtv', 'Shubh TV'),
    ('9xm', '9XM'),
    ('9xjalwa', '9XM Jalwa'),
    ('9xm_jalwa', '9XM Jalwa'),
    ('9x_jalwa', '9XM Jalwa'),
    ('9xtashan', '9XM Tashan'),
    ('9xm_tashan', '9XM Tashan'),
    ('9x_tashan', '9XM Tashan'),
    ('9xjhakaas', '9XM Jhakaas'),
    ('9xm_jhakaas', '9XM Jhakaas'),
    ('9x_jhakaas', '9XM Jhakaas'),
    ('gtcnews', 'GTC News'),
    ('gtc_news', 'GTC News'),
    ('gtcpunjabi', 'GTC Punjabi'),
    ('gtc_punjabi', 'GTC Punjabi'),
    ('punjabshort', 'Punjabi Shorts'),
    ('punjabi_shorts', 'Punjabi Shorts'),
    ('b4umo001', 'B4U Movies'),
    ('b4um001', 'B4U Music'),
    ('b4ua001', 'B4U Kadak'),
    ('b4u_bhojpuri', 'B4U Bhojpuri'),
    ('bollywoodmasala', 'Bollywood Masala'),
    ('vetocricketlive', 'Veto Cricket Live')
) AS mappings(candidate, channel)
),
stream_host_path_map AS (
SELECT * FROM (VALUES
    ('tennis-vod.akamaized.net', '693ac32e6ca0d700028320f5', 'Davis VOD (693ac)'),
    ('vetointv.akamaized.net', 'dreamboat-ch01', 'Weightlifting (dreamboat-ch01)'),
    ('vetostreams.akamaized.net', 'indiatv', 'India TV'),
    ('vetostreams.akamaized.net:443', 'indiatv', 'India TV'),
    ('vetostreams.akamaized.net', 'upgovlive', 'UP Government Live'),
    ('vetostreams.akamaized.net', 'ukgovlive', 'UK Government Live')
) AS mappings(host, candidate, channel)
),
selected AS (
    SELECT *, 
lower(
    CASE
        WHEN path LIKE '%vglive-sk-%'
            THEN regexp_extract(path, '(vglive-sk-[0-9]+)', 1)
        WHEN path LIKE '%/%' THEN
            CASE
                WHEN lower(split_part(ltrim(path, '/'), '/', 1)) IN ('', 'hls', 'live', 'nntv', 'stream', 'v1')
                    THEN split_part(ltrim(path, '/'), '/', 2)
                ELSE split_part(ltrim(path, '/'), '/', 1)
            END
        ELSE regexp_replace(
            regexp_extract(path, '([^/]+)\.ts$', 1),
            '[_-]?(1080p?|720p?|480p?|360p?|\d+)$',
            ''
        )
    END
)
 AS candidate,
        CASE WHEN host LIKE '%vod%' OR lower(path) LIKE '%/vod/%'
             THEN nullif(lower(split_part(ltrim(path,'/'),'/',4)), '') END AS video_key,
        nullif(regexp_extract(queryStr, '(?i)(?:^|[?&])content_title=([^&]+)', 1), '') AS title_encoded
    FROM stream_day_requests
    WHERE cli_ip = COALESCE(
        (SELECT target_ip FROM settings),
        (SELECT cli_ip FROM stream_day_requests
         WHERE is_ts AND cli_ip IS NOT NULL
         GROUP BY cli_ip
         ORDER BY abs(count(*) - 200), cli_ip
         LIMIT 1)
    )
), titled AS (
    SELECT * EXCLUDE (title_encoded),
        coalesce(try(url_decode(replace(title_encoded, '+', ' '))), replace(title_encoded, '+', ' ')) AS title
    FROM selected
), title_map AS (
    SELECT host, video_key, min(title) AS title
    FROM titled WHERE video_key IS NOT NULL AND title IS NOT NULL
    GROUP BY 1, 2 HAVING count(DISTINCT title)=1
)
SELECT date_trunc('minute', epoch_ms(CAST(floor((r.req_epoch + 19800)*1000) AS BIGINT))) AS minute_ist,
       r.cli_ip,
       coalesce(hp.channel, h.channel, p.channel, r.host) AS channel_or_host,
       coalesce(r.title, t.title) AS content_title,
       r.video_key,
       coalesce(u.device_type, 'Unknown') AS device_type,
       coalesce(u.brand, 'Unknown') AS brand,
       coalesce(u.model, 'Unknown') AS model,
       coalesce(nullif(u.os, ''), 'Unknown') AS os,
       count(*) AS segment_requests
FROM titled r
LEFT JOIN title_map t ON r.host=t.host AND r.video_key=t.video_key
LEFT JOIN stream_host_path_map hp ON r.host=hp.host AND r.candidate=hp.candidate
LEFT JOIN stream_host_map h ON r.host=h.host
LEFT JOIN stream_path_map p ON r.candidate=p.candidate
LEFT JOIN stream_ua_lookup u ON u.ua_norm = NULLIF(trim(regexp_replace(regexp_replace(COALESCE(try(url_decode(COALESCE(try(url_decode(COALESCE(try(url_decode(COALESCE(try(url_decode(COALESCE(try(url_decode(CAST(r.raw_ua AS VARCHAR))), CAST(r.raw_ua AS VARCHAR)))), COALESCE(try(url_decode(CAST(r.raw_ua AS VARCHAR))), CAST(r.raw_ua AS VARCHAR))))), COALESCE(try(url_decode(COALESCE(try(url_decode(CAST(r.raw_ua AS VARCHAR))), CAST(r.raw_ua AS VARCHAR)))), COALESCE(try(url_decode(CAST(r.raw_ua AS VARCHAR))), CAST(r.raw_ua AS VARCHAR)))))), COALESCE(try(url_decode(COALESCE(try(url_decode(COALESCE(try(url_decode(CAST(r.raw_ua AS VARCHAR))), CAST(r.raw_ua AS VARCHAR)))), COALESCE(try(url_decode(CAST(r.raw_ua AS VARCHAR))), CAST(r.raw_ua AS VARCHAR))))), COALESCE(try(url_decode(COALESCE(try(url_decode(CAST(r.raw_ua AS VARCHAR))), CAST(r.raw_ua AS VARCHAR)))), COALESCE(try(url_decode(CAST(r.raw_ua AS VARCHAR))), CAST(r.raw_ua AS VARCHAR))))))), COALESCE(try(url_decode(COALESCE(try(url_decode(COALESCE(try(url_decode(COALESCE(try(url_decode(CAST(r.raw_ua AS VARCHAR))), CAST(r.raw_ua AS VARCHAR)))), COALESCE(try(url_decode(CAST(r.raw_ua AS VARCHAR))), CAST(r.raw_ua AS VARCHAR))))), COALESCE(try(url_decode(COALESCE(try(url_decode(CAST(r.raw_ua AS VARCHAR))), CAST(r.raw_ua AS VARCHAR)))), COALESCE(try(url_decode(CAST(r.raw_ua AS VARCHAR))), CAST(r.raw_ua AS VARCHAR)))))), COALESCE(try(url_decode(COALESCE(try(url_decode(COALESCE(try(url_decode(CAST(r.raw_ua AS VARCHAR))), CAST(r.raw_ua AS VARCHAR)))), COALESCE(try(url_decode(CAST(r.raw_ua AS VARCHAR))), CAST(r.raw_ua AS VARCHAR))))), COALESCE(try(url_decode(COALESCE(try(url_decode(CAST(r.raw_ua AS VARCHAR))), CAST(r.raw_ua AS VARCHAR)))), COALESCE(try(url_decode(CAST(r.raw_ua AS VARCHAR))), CAST(r.raw_ua AS VARCHAR)))))), '\+', ' ', 'g'), '\s+', ' ', 'g')), '')
WHERE r.is_ts AND isfinite(r.req_epoch)
GROUP BY ALL
ORDER BY minute_ist, segment_requests DESC, channel_or_host;

#!/usr/bin/env python3
"""Extract one IST day of VOD STREAM query-string evidence from a raw Parquet partition."""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb


HERE = Path(__file__).resolve().parent
ETL_ROOT = HERE.parents[1]
DEFAULT_UA_LOOKUP = ETL_ROOT / "output" / "device_decode" / "ua_decode_lookup_both_all.parquet"


def ua_norm_sql(column_expr: str) -> str:
    """Match the normalization used to build the shared UA decode lookup."""
    decoded_expr = f"CAST({column_expr} AS VARCHAR)"
    for _ in range(5):
        decoded_expr = f"COALESCE(try(url_decode({decoded_expr})), {decoded_expr})"
    return (
        "NULLIF(trim(regexp_replace(regexp_replace("
        f"{decoded_expr}, '\\+', ' ', 'g'), '\\s+', ' ', 'g')), '')"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Export one day of VOD STREAM query-string events.")
    parser.add_argument("--input", type=Path, required=True, help="Raw STREAM Parquet file for the target date.")
    parser.add_argument("--date", required=True, help="Target IST date (YYYY-MM-DD).")
    parser.add_argument("--out", type=Path, required=True, help="Daily VOD event CSV output.")
    parser.add_argument(
        "--ua-lookup",
        type=Path,
        default=DEFAULT_UA_LOOKUP,
        help="Shared exact-UA decode lookup Parquet.",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Aggregate segment requests to minute/viewer/content rows for dashboards.",
    )
    args = parser.parse_args()
    if not args.input.exists():
        raise FileNotFoundError(f"Raw Parquet was not found: {args.input}")
    if not args.ua_lookup.exists():
        raise FileNotFoundError(f"UA decode lookup was not found: {args.ua_lookup}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    query_param = lambda name: f"url_decode(regexp_extract(queryStr, '(?i)(?:^|[?&]){name}=([^&]+)', 1))"
    timestamp = "to_timestamp(try_cast(reqTimeSec AS DOUBLE)) AT TIME ZONE 'Asia/Kolkata'"
    # The fourth path component is the content code used by both a VOD manifest
    # and its HLS .ts segments, e.g. .../2026/07/20atoa8e/... .
    content_code = "lower(split_part(ltrim(COALESCE(reqPath, ''), '/'), '/', 4))"
    connection = duckdb.connect(":memory:")
    try:
        source_columns = {
            row[0]
            for row in connection.execute(
                "DESCRIBE SELECT * FROM read_parquet(?)", [str(args.input)]
            ).fetchall()
        }
        ua_source = "UA" if "UA" in source_columns else "''"
        ua_norm = ua_norm_sql(ua_source)
        output_sql = str(args.out).replace("'", "''")
        if args.compact:
            output_projection = """
                SELECT
                    log_date,
                    minute_ist,
                    min(request_ist) AS request_ist,
                    max(request_ist) AS last_request_ist,
                    content_title,
                    category_name,
                    content_type,
                    channel,
                    platform,
                    device,
                    user_agent,
                    decode_status,
                    decode_confidence,
                    decoded_device_type,
                    decoded_form_factor,
                    decoded_brand,
                    decoded_model,
                    decoded_os,
                    decoded_browser,
                    decoded_player,
                    session_id,
                    device_id,
                    cli_ip,
                    country,
                    state,
                    city,
                    asn,
                    req_host,
                    arg_min(req_path, request_ist) AS req_path,
                    string_agg(DISTINCT status_code, ', ' ORDER BY status_code) AS status_code,
                    string_agg(DISTINCT cache_status, ', ' ORDER BY cache_status) AS cache_status,
                    request_kind,
                    1 AS is_media_segment,
                    sum(is_successful_segment) AS successful_segment_count,
                    sum(segment_seconds) AS segment_seconds,
                    sum(request_watch_hours) AS request_watch_hours,
                    sum(delivered_watch_hours) AS delivered_watch_hours,
                    arg_min(query_string, request_ist) AS query_string,
                    content_code,
                    identity_source,
                    max(content_mapping_evidence) AS content_mapping_evidence,
                    count(*) AS segment_count
                FROM mapped_segments
                GROUP BY
                    log_date, minute_ist, content_title, category_name, content_type,
                    channel, platform, device, user_agent, decode_status,
                    decode_confidence, decoded_device_type, decoded_form_factor,
                    decoded_brand, decoded_model, decoded_os, decoded_browser,
                    decoded_player, session_id, device_id, cli_ip,
                    country, state, city, asn, req_host, request_kind,
                    content_code, identity_source
            """
        else:
            output_projection = """
                SELECT
                    *,
                    request_ist AS last_request_ist,
                    is_successful_segment AS successful_segment_count,
                    1 AS segment_count
                FROM mapped_segments
            """
        connection.execute(
            f"""
            COPY (
                WITH source AS (
                    SELECT
                        *,
                        try_cast(reqTimeSec AS DOUBLE) AS req_time_seconds,
                        {timestamp} AS request_timestamp,
                        {content_code} AS content_code,
                        lower(COALESCE(reqHost, '')) AS req_host_key,
                        COALESCE(NULLIF(cliIP, ''), '') AS cli_ip_key,
                        COALESCE(CAST({ua_source} AS VARCHAR), '') AS user_agent,
                        {ua_norm} AS ua_norm,
                        COALESCE(NULLIF({query_param('content_title')}, ''), '') AS query_content_title,
                        COALESCE(NULLIF({query_param('category_name')}, ''), '') AS query_category_name,
                        COALESCE(NULLIF({query_param('content_type')}, ''), '') AS query_content_type,
                        COALESCE(NULLIF({query_param('channel_name')}, ''), NULLIF({query_param('channel')}, ''), '') AS query_channel,
                        COALESCE(NULLIF({query_param('platform')}, ''), '') AS query_platform,
                        COALESCE(NULLIF({query_param('device')}, ''), '') AS query_device,
                        COALESCE(NULLIF({query_param('session_id')}, ''), '') AS query_session_id,
                        COALESCE(NULLIF({query_param('device_id')}, ''), '') AS query_device_id
                    FROM read_parquet(?)
                    WHERE CAST({timestamp} AS DATE) = CAST(? AS DATE)
                ),
                ua_lookup AS (
                    SELECT * EXCLUDE (lookup_rank)
                    FROM (
                        SELECT
                            ua_norm,
                            decode_status,
                            confidence,
                            device_type,
                            form_factor,
                            brand,
                            model,
                            os_name,
                            os_version,
                            browser_name,
                            browser_version,
                            app_player,
                            api_device_type,
                            api_brand,
                            api_model,
                            api_os_name,
                            api_browser_name,
                            api_browser_version,
                            row_number() OVER (
                                PARTITION BY ua_norm ORDER BY decoded_at_utc DESC NULLS LAST
                            ) AS lookup_rank
                        FROM read_parquet(?)
                        WHERE NULLIF(trim(COALESCE(ua_norm, '')), '') IS NOT NULL
                    )
                    WHERE lookup_rank = 1
                ),
                manifest_events AS (
                    SELECT
                        req_host_key,
                        content_code,
                        cli_ip_key,
                        req_time_seconds,
                        query_content_title AS content_title,
                        query_category_name AS category_name,
                        query_content_type AS content_type,
                        query_channel AS channel,
                        query_platform AS platform,
                        query_device AS device,
                        query_session_id AS session_id,
                        query_device_id AS device_id,
                        COALESCE(queryStr, '') AS query_string
                    FROM source
                    WHERE lower(query_content_type) = 'vod'
                      AND regexp_matches(lower(COALESCE(reqPath, '')), '\\.m3u8(?:\\?|$)')
                      AND content_code <> ''
                ),
                content_groups AS (
                    SELECT
                        req_host_key,
                        content_code,
                        content_title,
                        category_name,
                        content_type,
                        channel,
                        count(*) AS evidence_count,
                        max(req_time_seconds) AS latest_evidence
                    FROM manifest_events
                    GROUP BY ALL
                ),
                content_lookup AS (
                    SELECT * EXCLUDE (content_rank)
                    FROM (
                        SELECT
                            *,
                            row_number() OVER (
                                PARTITION BY req_host_key, content_code
                                ORDER BY evidence_count DESC, latest_evidence DESC
                            ) AS content_rank
                        FROM content_groups
                    )
                    WHERE content_rank = 1
                ),
                segments AS (
                    SELECT *
                    FROM source
                    WHERE content_code <> ''
                      AND regexp_matches(lower(COALESCE(reqPath, '')), '\\.ts(?:\\?|$)')
                ),
                segments_with_viewer AS (
                    SELECT
                        segment.*,
                        viewer.content_title AS viewer_content_title,
                        viewer.category_name AS viewer_category_name,
                        viewer.content_type AS viewer_content_type,
                        viewer.channel AS viewer_channel,
                        viewer.platform AS viewer_platform,
                        viewer.device AS viewer_device,
                        viewer.session_id AS viewer_session_id,
                        viewer.device_id AS viewer_device_id,
                        viewer.query_string AS viewer_query_string
                    FROM segments AS segment
                    ASOF LEFT JOIN manifest_events AS viewer
                        ON segment.req_host_key = viewer.req_host_key
                       AND segment.content_code = viewer.content_code
                       AND segment.cli_ip_key = viewer.cli_ip_key
                       AND segment.req_time_seconds >= viewer.req_time_seconds
                ),
                mapped_segments AS (
                SELECT
                    strftime(segment.request_timestamp, '%Y-%m-%d') AS log_date,
                    strftime(date_trunc('minute', segment.request_timestamp), '%Y-%m-%d %H:%M:%S') AS minute_ist,
                    strftime(segment.request_timestamp, '%Y-%m-%d %H:%M:%S.%f') AS request_ist,
                    COALESCE(NULLIF(segment.query_content_title, ''), NULLIF(segment.viewer_content_title, ''), NULLIF(content.content_title, ''), 'Unknown / Unmarked') AS content_title,
                    COALESCE(NULLIF(segment.query_category_name, ''), NULLIF(segment.viewer_category_name, ''), NULLIF(content.category_name, ''), 'Unknown / Unmarked') AS category_name,
                    COALESCE(NULLIF(segment.query_content_type, ''), NULLIF(segment.viewer_content_type, ''), NULLIF(content.content_type, ''), 'Vod') AS content_type,
                    COALESCE(NULLIF(segment.query_channel, ''), NULLIF(segment.viewer_channel, ''), 'Unknown / Unmarked') AS channel,
                    COALESCE(NULLIF(segment.query_platform, ''), NULLIF(segment.viewer_platform, ''), 'Unknown / NA') AS platform,
                    COALESCE(NULLIF(segment.query_device, ''), NULLIF(segment.viewer_device, ''), 'Unknown / NA') AS device,
                    segment.user_agent,
                    COALESCE(NULLIF(ua.decode_status, ''), 'not_in_lookup') AS decode_status,
                    COALESCE(NULLIF(ua.confidence, ''), 'Unknown / NA') AS decode_confidence,
                    COALESCE(NULLIF(ua.device_type, ''), NULLIF(ua.api_device_type, ''), 'Unknown / NA') AS decoded_device_type,
                    COALESCE(NULLIF(ua.form_factor, ''), 'Unknown / NA') AS decoded_form_factor,
                    COALESCE(NULLIF(ua.brand, ''), NULLIF(ua.api_brand, ''), 'Unknown / NA') AS decoded_brand,
                    COALESCE(NULLIF(ua.model, ''), NULLIF(ua.api_model, ''), 'Unknown / NA') AS decoded_model,
                    COALESCE(
                        NULLIF(trim(
                            COALESCE(NULLIF(ua.os_name, ''), NULLIF(ua.api_os_name, ''), '')
                            || ' ' || COALESCE(NULLIF(ua.os_version, ''), '')
                        ), ''),
                        'Unknown / NA'
                    ) AS decoded_os,
                    COALESCE(
                        NULLIF(trim(
                            COALESCE(NULLIF(ua.browser_name, ''), NULLIF(ua.api_browser_name, ''), '')
                            || ' ' || COALESCE(NULLIF(ua.browser_version, ''), NULLIF(ua.api_browser_version, ''), '')
                        ), ''),
                        'Unknown / NA'
                    ) AS decoded_browser,
                    COALESCE(NULLIF(ua.app_player, ''), 'Unknown / NA') AS decoded_player,
                    COALESCE(NULLIF(segment.query_session_id, ''), NULLIF(segment.viewer_session_id, ''), '') AS session_id,
                    COALESCE(NULLIF(segment.query_device_id, ''), NULLIF(segment.viewer_device_id, ''), '') AS device_id,
                    segment.cli_ip_key AS cli_ip,
                    COALESCE(NULLIF(url_decode(segment.country), ''), 'Unknown / NA') AS country,
                    COALESCE(NULLIF(url_decode(segment.state), ''), 'Unknown / NA') AS state,
                    COALESCE(NULLIF(url_decode(segment.city), ''), 'Unknown / NA') AS city,
                    COALESCE(NULLIF(segment.asn, ''), 'Unknown / NA') AS asn,
                    COALESCE(NULLIF(segment.reqHost, ''), 'Unknown / NA') AS req_host,
                    COALESCE(NULLIF(segment.reqPath, ''), 'Unknown / NA') AS req_path,
                    COALESCE(NULLIF(segment.statusCode, ''), 'Unknown / NA') AS status_code,
                    COALESCE(NULLIF(segment.cacheStatus, ''), 'Unknown / NA') AS cache_status,
                    'media_segment' AS request_kind,
                    1 AS is_media_segment,
                    CASE
                        WHEN try_cast(segment.statusCode AS INTEGER) BETWEEN 200 AND 299 THEN 1
                        ELSE 0
                    END AS is_successful_segment,
                    6.0 AS segment_seconds,
                    6.0 / 3600.0 AS request_watch_hours,
                    CASE
                        WHEN try_cast(segment.statusCode AS INTEGER) BETWEEN 200 AND 299
                            THEN 6.0 / 3600.0
                        ELSE 0.0
                    END AS delivered_watch_hours,
                    COALESCE(NULLIF(segment.queryStr, ''), NULLIF(segment.viewer_query_string, ''), '') AS query_string,
                    segment.content_code,
                    CASE
                        WHEN segment.query_session_id <> '' OR segment.query_device_id <> '' THEN 'segment_query'
                        WHEN segment.viewer_session_id <> '' OR segment.viewer_device_id <> '' THEN 'same_cli_manifest'
                        ELSE 'unavailable'
                    END AS identity_source,
                    COALESCE(content.evidence_count, 0) AS content_mapping_evidence
                FROM segments_with_viewer AS segment
                LEFT JOIN content_lookup AS content
                    ON segment.req_host_key = content.req_host_key
                   AND segment.content_code = content.content_code
                LEFT JOIN ua_lookup AS ua
                    ON segment.ua_norm = ua.ua_norm
                WHERE lower(COALESCE(
                        NULLIF(segment.query_content_type, ''),
                        NULLIF(segment.viewer_content_type, ''),
                        NULLIF(content.content_type, ''),
                        ''
                    )) = 'vod'
                   OR (
                        COALESCE(
                            NULLIF(segment.query_content_type, ''),
                            NULLIF(segment.viewer_content_type, ''),
                            NULLIF(content.content_type, ''),
                            ''
                        ) = ''
                        AND regexp_matches(segment.req_host_key, '(^|[.-])vod([.-]|$)')
                   )
                )
                {output_projection}
            ) TO '{output_sql}' (FORMAT CSV, HEADER TRUE, DELIMITER ',')
            """,
            [str(args.input), args.date, str(args.ua_lookup)],
        )
        count = connection.execute("SELECT count(*) FROM read_csv_auto(?)", [str(args.out)]).fetchone()[0]
    finally:
        connection.close()
    grain = "minute activity" if args.compact else "request"
    print(f"Wrote {args.out} with {count:,} VOD {grain} rows for {args.date}.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Independently count CLI IPs observed on VOD-named request hosts."""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export distinct CLI IPs for request hosts containing a VOD marker."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--date", required=True, help="IST date in YYYY-MM-DD format.")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--host-contains", default="vod")
    args = parser.parse_args()

    if not args.input.exists():
        raise FileNotFoundError(f"Raw Parquet was not found: {args.input}")
    args.out.parent.mkdir(parents=True, exist_ok=True)

    timestamp = "to_timestamp(try_cast(reqTimeSec AS DOUBLE)) AT TIME ZONE 'Asia/Kolkata'"
    output_sql = str(args.out).replace("'", "''")
    connection = duckdb.connect(":memory:")
    try:
        connection.execute(
            f"""
            COPY (
                SELECT
                    lower(trim(reqHost)) AS req_host,
                    trim(cliIP) AS cli_ip,
                    count(*) AS total_requests,
                    count(*) FILTER (
                        WHERE regexp_matches(lower(COALESCE(reqPath, '')), '\\.m3u8(?:\\?|$)')
                    ) AS manifest_requests,
                    count(*) FILTER (
                        WHERE regexp_matches(lower(COALESCE(reqPath, '')), '\\.ts(?:\\?|$)')
                    ) AS ts_requests,
                    count(*) FILTER (
                        WHERE regexp_matches(lower(COALESCE(reqPath, '')), '\\.ts(?:\\?|$)')
                          AND try_cast(statusCode AS INTEGER) BETWEEN 200 AND 299
                    ) AS successful_ts_requests,
                    strftime(min({timestamp}), '%Y-%m-%d %H:%M:%S.%f') AS first_request_ist,
                    strftime(max({timestamp}), '%Y-%m-%d %H:%M:%S.%f') AS last_request_ist
                FROM read_parquet(?)
                WHERE CAST({timestamp} AS DATE) = CAST(? AS DATE)
                  AND reqHost IS NOT NULL
                  AND contains(lower(reqHost), lower(?))
                  AND cliIP IS NOT NULL
                  AND length(trim(cliIP)) > 0
                GROUP BY lower(trim(reqHost)), trim(cliIP)
                ORDER BY req_host, cli_ip
            ) TO '{output_sql}' (FORMAT CSV, HEADER TRUE)
            """,
            [str(args.input), args.date, args.host_contains],
        )
        totals = connection.execute(
            """
            SELECT
                count(*) AS distinct_host_ip_pairs,
                count(DISTINCT cli_ip) AS distinct_cli_ips,
                count(DISTINCT cli_ip) FILTER (WHERE ts_requests > 0)
                    AS distinct_ts_cli_ips,
                count(DISTINCT cli_ip) FILTER (WHERE successful_ts_requests > 0)
                    AS distinct_successful_ts_cli_ips,
                sum(total_requests) AS total_requests,
                sum(ts_requests) AS ts_requests,
                sum(successful_ts_requests) AS successful_ts_requests
            FROM read_csv_auto(?)
            """,
            [str(args.out)],
        ).fetchone()
        hosts = connection.execute(
            """
            SELECT
                req_host,
                count(*) AS distinct_cli_ips,
                count(*) FILTER (WHERE ts_requests > 0)
                    AS distinct_ts_cli_ips,
                count(*) FILTER (WHERE successful_ts_requests > 0)
                    AS distinct_successful_ts_cli_ips,
                sum(total_requests) AS total_requests,
                sum(ts_requests) AS ts_requests,
                sum(successful_ts_requests) AS successful_ts_requests
            FROM read_csv_auto(?)
            GROUP BY req_host
            ORDER BY distinct_cli_ips DESC, req_host
            """,
            [str(args.out)],
        ).fetchall()
    finally:
        connection.close()

    print(
        "Host/IP pairs: {:,}; distinct CLI IPs: {:,}; all-status .ts CLI IPs: {:,}; "
        "successful .ts CLI IPs: {:,}; requests: {:,}; all-status .ts requests: {:,}; "
        "successful .ts requests: {:,}.".format(*totals)
    )
    for host, cli_ips, all_ts_cli_ips, successful_ts_cli_ips, requests, ts_requests, successful_ts_requests in hosts:
        print(
            f"{host}: {cli_ips:,} CLI IPs; {all_ts_cli_ips:,} all-status .ts CLI IPs; "
            f"{successful_ts_cli_ips:,} successful .ts CLI IPs; {requests:,} requests; "
            f"{ts_requests:,} all-status .ts requests; "
            f"{successful_ts_requests:,} successful .ts requests."
        )
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()

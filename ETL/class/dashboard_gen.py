#!/usr/bin/env python3
"""Generate the Phase 1 Watch Hours dashboard from the canonical daily marts.

Expected input schema (Parquet, one row per daily geographic channel aggregate):
    log_date                  VARCHAR, ISO date (YYYY-MM-DD)
    source                    VARCHAR, e.g. fast or stream
    country                   VARCHAR, geographic region code/name; null is allowed
    state                     VARCHAR, state/administrative region; null is allowed
    channel_name              VARCHAR, canonical channel label; null is allowed
    raw_watch_hours           numeric, watch hours across all status codes
    approx_unique_ips         numeric, approximate viewer count for the aggregate

FAST platform input schema (used only when a FAST platform is selected):
    log_date, source, country, state, channel_name, platform_name/platform_key,
    raw_watch_hours

The current canonical input is:
    output/watch_hours/daily_tables/channel_geo_daily.parquet

Device/OS input schema (Parquet, source and channel scope rows):
    log_date, source, channel_name, dimension, label, scope, watch_hours
    dimension must contain: device, model, os, os_detail

True Device/OS hierarchy inputs:
    user_agents_daily.parquet:
        log_date, source, userAgent, raw_ts_rows
    ua_decode_lookup_both_all.parquet:
        ua_hash plus decoded device/model/OS identity columns
    fast_platform_channel_ua_device_daily.parquet:
        log_date, source, platform, channel, decoded device/model/OS labels,
        raw_ts_rows

The hierarchy payload keeps Device -> Model -> OS -> OS Version relationships.
Source-level FAST and STREAM use decoded user-agent rows. FAST channel/platform
selections use the joint FAST mart. STREAM channel data exposes Device Type only;
geographic Device/OS drilldown is not claimed because no joint mart exists.

Network/ASN input schema (source/date grain):
    log_date, source, asn, as_name, as_country, as_domain, asn_type,
    lookup_status, raw_ts_rows, approx_unique_ips
    Network watch hours are all-status raw_ts_rows * 6 seconds / 3600.

The base KPI uses the canonical channel + geography mart. A selected FAST
platform switches to the documented FAST platform + channel geography mart;
the UI labels that selected-platform result as platform-tagged FAST data.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import duckdb


HERE = Path(__file__).resolve().parent
ETL_ROOT = HERE.parent
DEFAULT_INPUT = ETL_ROOT / "output" / "watch_hours" / "daily_tables" / "channel_geo_daily.parquet"
DEFAULT_PLATFORM_INPUT = ETL_ROOT / "output" / "watch_hours" / "concurrency" / "fast_platform_channel_geo_daily.parquet"
DEFAULT_IDENTITY_INPUT = ETL_ROOT / "output" / "identity" / "identity_daily.parquet"
DEFAULT_CONCURRENCY_INPUT = ETL_ROOT / "output" / "watch_hours" / "concurrency" / "identity_minute.parquet"
DEFAULT_UA_INPUT = ETL_ROOT / "output" / "master" / "data" / "master_ua_daily.parquet"
DEFAULT_UA_SOURCE_INPUT = ETL_ROOT / "output" / "watch_hours" / "daily_tables" / "user_agents_daily.parquet"
DEFAULT_UA_LOOKUP_INPUT = ETL_ROOT / "output" / "device_decode" / "ua_decode_lookup_both_all.parquet"
DEFAULT_FAST_UA_INPUT = ETL_ROOT / "output" / "watch_hours" / "concurrency" / "fast_platform_channel_ua_device_daily.parquet"
DEFAULT_ASN_INPUT = ETL_ROOT / "output" / "master" / "data" / "master_asn_daily.parquet"
MASTER_DASHBOARD_GENERATOR = ETL_ROOT / "src" / "dashboards" / "masterDashboard" / "generate_master_dashboard.py"
DEFAULT_OUTPUT = HERE / "watch_hours_phase1.html"
REQUIRED_COLUMNS = {
    "log_date",
    "source",
    "country",
    "state",
    "channel_name",
    "raw_watch_hours",
    "approx_unique_ips",
}
PLATFORM_COLUMNS = {"platform_name", "platform_key"}
IDENTITY_COLUMNS = {"source", "log_date", "total_devices", "total_sessions"}
CONCURRENCY_COLUMNS = {"log_date", "source", "minute_ist", "distinct_cliips", "platform_name", "channel_name"}
UA_COLUMNS = {"log_date", "source", "channel_name", "dimension", "label", "scope", "watch_hours"}
ASN_COLUMNS = {
    "log_date", "source", "asn", "as_name", "as_country", "as_domain",
    "asn_type", "lookup_status", "raw_ts_rows", "approx_unique_ips",
}


def common_publish_through(*datasets: list[list[Any]]) -> str:
    """Return the latest complete common date, capped at yesterday."""
    latest_dates = [max(str(row[0]) for row in rows) for rows in datasets if rows]
    if not latest_dates:
        raise ValueError("Dashboard inputs contain no dated rows.")
    return min((date.today() - timedelta(days=1)).isoformat(), *latest_dates)


def through_date(rows: list[list[Any]], end_date: str) -> list[list[Any]]:
    return [row for row in rows if str(row[0]) <= end_date]


def parquet_columns(path: Path) -> set[str]:
    if not path.exists():
        raise FileNotFoundError(f"Input Parquet was not found: {path}")
    connection = duckdb.connect(":memory:")
    try:
        return {
            row[0]
            for row in connection.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(path)]).fetchall()
        }
    finally:
        connection.close()


def validate_input(path: Path) -> set[str]:
    columns = parquet_columns(path)
    missing = sorted(REQUIRED_COLUMNS - columns)
    if missing:
        raise ValueError(f"Input Parquet is missing required column(s): {', '.join(missing)}")
    return columns


def validate_platform_input(path: Path) -> set[str]:
    columns = validate_input(path)
    if not PLATFORM_COLUMNS.intersection(columns):
        expected = " or ".join(sorted(PLATFORM_COLUMNS))
        raise ValueError(f"FAST platform Parquet needs one of: {expected}")
    return columns


def load_rows(path: Path) -> list[list[Any]]:
    """Read and aggregate only the six columns used by the dashboard."""
    connection = duckdb.connect(":memory:")
    try:
        rows = connection.execute(
            """
            SELECT
                CAST(log_date AS VARCHAR) AS log_date,
                COALESCE(NULLIF(TRIM(source), ''), 'Unknown') AS source,
                COALESCE(NULLIF(TRIM(country), ''), 'Unknown / NA') AS region,
                COALESCE(NULLIF(TRIM(state), ''), 'Unknown / NA') AS state,
                COALESCE(NULLIF(TRIM(channel_name), ''), 'Unknown / NA') AS channel_name,
                SUM(CAST(COALESCE(raw_watch_hours, 0) AS DOUBLE)) AS watch_hours
                ,SUM(CAST(COALESCE(approx_unique_ips, 0) AS DOUBLE)) AS viewers
            FROM read_parquet(?)
            WHERE log_date IS NOT NULL
            GROUP BY 1, 2, 3, 4, 5
            """,
            [str(path)],
        ).fetchall()
    finally:
        connection.close()
    return [[str(log_date), str(source), str(region), str(state), str(channel), float(hours), float(viewers)] for log_date, source, region, state, channel, hours, viewers in rows]


def load_platform_rows(path: Path) -> list[list[Any]]:
    """Read FAST platform + channel geography rows for the optional FAST filter."""
    columns = validate_platform_input(path)
    if {"platform_name", "platform_key"}.issubset(columns):
        platform_expression = "COALESCE(NULLIF(TRIM(platform_name), ''), NULLIF(TRIM(platform_key), ''), 'Unknown / NA')"
    else:
        platform_column = next(iter(PLATFORM_COLUMNS.intersection(columns)))
        platform_expression = f"COALESCE(NULLIF(TRIM({platform_column}), ''), 'Unknown / NA')"
    connection = duckdb.connect(":memory:")
    try:
        rows = connection.execute(
            f"""
            SELECT
                CAST(log_date AS VARCHAR) AS log_date,
                'fast' AS source,
                COALESCE(NULLIF(TRIM(country), ''), 'Unknown / NA') AS region,
                COALESCE(NULLIF(TRIM(state), ''), 'Unknown / NA') AS state,
                COALESCE(NULLIF(TRIM(channel_name), ''), 'Unknown / NA') AS channel_name,
                SUM(CAST(COALESCE(raw_watch_hours, 0) AS DOUBLE)) AS watch_hours,
                SUM(CAST(COALESCE(approx_unique_ips, 0) AS DOUBLE)) AS viewers,
                {platform_expression} AS platform
            FROM read_parquet(?)
            WHERE log_date IS NOT NULL
                GROUP BY 1, 2, 3, 4, 5, 8
            """,
            [str(path)],
        ).fetchall()
    finally:
        connection.close()
    return [[str(log_date), str(source), str(region), str(state), str(channel), float(hours), float(viewers), str(platform)] for log_date, source, region, state, channel, hours, viewers, platform in rows]


def load_identity_rows(path: Path) -> list[list[Any]]:
    """Read daily STREAM device/session identity counts for the grouped chart."""
    columns = parquet_columns(path)
    missing = sorted(IDENTITY_COLUMNS - columns)
    if missing:
        raise ValueError(f"Identity Parquet is missing required column(s): {', '.join(missing)}")
    connection = duckdb.connect(":memory:")
    try:
        rows = connection.execute(
            """
            SELECT
                CAST(log_date AS VARCHAR) AS log_date,
                COALESCE(NULLIF(TRIM(source), ''), 'Unknown') AS source,
                SUM(CAST(COALESCE(total_devices, 0) AS BIGINT)) AS devices,
                SUM(CAST(COALESCE(total_sessions, 0) AS BIGINT)) AS sessions
            FROM read_parquet(?)
            WHERE log_date IS NOT NULL
            GROUP BY 1, 2
            ORDER BY 1, 2
            """,
            [str(path)],
        ).fetchall()
    finally:
        connection.close()
    return [[str(log_date), str(source), int(devices or 0), int(sessions or 0)] for log_date, source, devices, sessions in rows]


def load_concurrency_rows(path: Path, start_date: str | None = None, end_date: str | None = None) -> list[list[Any]]:
    """Read Audience Ops identity-minute cliIP counts; gaps remain visible in the browser."""
    columns = parquet_columns(path)
    missing = sorted(CONCURRENCY_COLUMNS - columns)
    if missing:
        raise ValueError(f"Concurrency Parquet is missing required column(s): {', '.join(missing)}")
    connection = duckdb.connect(":memory:")
    try:
        rows = connection.execute(
            """
            SELECT
                CAST(log_date AS VARCHAR) AS log_date,
                LOWER(COALESCE(NULLIF(TRIM(source), ''), 'unknown')) AS source,
                CAST(minute_ist AS VARCHAR) AS minute_ist,
                COALESCE(NULLIF(TRIM(channel_name), ''), 'Unknown / NA') AS channel_name,
                COALESCE(NULLIF(TRIM(platform_name), ''), 'Unknown / NA') AS platform_name,
                SUM(CAST(COALESCE(distinct_cliips, 0) AS BIGINT)) AS users
            FROM read_parquet(?)
            WHERE log_date IS NOT NULL AND minute_ist IS NOT NULL
                AND (? IS NULL OR CAST(log_date AS DATE) >= CAST(? AS DATE))
                AND (? IS NULL OR CAST(log_date AS DATE) <= CAST(? AS DATE))
            GROUP BY 1, 2, 3, 4, 5
            ORDER BY 1, 2, 3, 4, 5
            """,
            [str(path), start_date, start_date, end_date, end_date],
        ).fetchall()
    finally:
        connection.close()
    return [[str(log_date), str(source), str(minute_ist), int(users or 0), str(channel), str(platform)] for log_date, source, minute_ist, channel, platform, users in rows]


def load_ua_rows(path: Path, start_date: str | None = None, end_date: str | None = None) -> list[list[Any]]:
    """Read only the four UA dimensions used by the Device/OS section."""
    columns = parquet_columns(path)
    missing = sorted(UA_COLUMNS - columns)
    if missing:
        raise ValueError(f"Device/OS Parquet is missing required column(s): {', '.join(missing)}")
    connection = duckdb.connect(":memory:")
    try:
        rows = connection.execute(
            """
            SELECT
                CAST(log_date AS VARCHAR) AS log_date,
                LOWER(COALESCE(NULLIF(TRIM(source), ''), 'unknown')) AS source,
                COALESCE(NULLIF(TRIM(channel_name), ''), '') AS channel_name,
                LOWER(TRIM(dimension)) AS dimension,
                COALESCE(NULLIF(TRIM(label), ''), 'Unknown / NA') AS label,
                LOWER(COALESCE(NULLIF(TRIM(scope), ''), 'source')) AS scope,
                SUM(CAST(COALESCE(watch_hours, 0) AS DOUBLE)) AS watch_hours
            FROM read_parquet(?)
            WHERE log_date IS NOT NULL
                AND LOWER(TRIM(dimension)) IN ('device', 'model', 'os', 'os_detail')
                AND (? IS NULL OR CAST(log_date AS DATE) >= CAST(? AS DATE))
                AND (? IS NULL OR CAST(log_date AS DATE) <= CAST(? AS DATE))
            GROUP BY 1, 2, 3, 4, 5, 6
            ORDER BY 1, 2, 4, 5
            """,
            [str(path), start_date, start_date, end_date, end_date],
        ).fetchall()
    finally:
        connection.close()
    return [
        [str(log_date), str(source), str(channel), str(dimension), str(label), str(scope), float(hours or 0)]
        for log_date, source, channel, dimension, label, scope, hours in rows
    ]


def load_ua_hierarchy_rows(
    source_path: Path,
    lookup_path: Path,
    fast_path: Path,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[list[Any]]:
    """Build truthful Device -> Model -> OS -> Version relationships from reusable marts."""
    spec = importlib.util.spec_from_file_location("_veto_master_dashboard_helpers", MASTER_DASHBOARD_GENERATOR)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load canonical UA helpers: {MASTER_DASHBOARD_GENERATOR}")
    helpers = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helpers)

    source_columns = {"log_date", "source", "userAgent", "raw_ts_rows"}
    lookup_columns = {
        "ua_hash", "decode_status", "device_type", "brand", "model", "model_code",
        "product_family", "generation", "os_name", "os_version", "os_family",
        "api_device_type", "api_brand", "api_model", "api_os_name", "api_os_version",
    }
    fast_columns = {
        "log_date", "source", "platform_key", "platform_name", "channel_name", "decode_status",
        "device_type_label", "brand_label", "model_label", "model_code_label",
        "product_family_label", "generation_label", "os_label", "os_family_label", "raw_ts_rows",
    }
    for path, required, label in (
        (source_path, source_columns, "source UA"),
        (lookup_path, lookup_columns, "UA lookup"),
        (fast_path, fast_columns, "FAST UA"),
    ):
        missing = sorted(required - parquet_columns(path))
        if missing:
            raise ValueError(f"{label} Parquet is missing required column(s): {', '.join(missing)}")

    connection = duckdb.connect(":memory:")
    try:
        source = connection.execute(
            """
            SELECT CAST(log_date AS VARCHAR) AS log_date,
                   LOWER(TRIM(source)) AS source,
                   COALESCE(userAgent, '') AS userAgent,
                   SUM(CAST(COALESCE(raw_ts_rows, 0) AS DOUBLE)) AS raw_ts_rows
            FROM read_parquet(?)
            WHERE log_date IS NOT NULL
              AND (? IS NULL OR CAST(log_date AS DATE) >= CAST(? AS DATE))
              AND (? IS NULL OR CAST(log_date AS DATE) <= CAST(? AS DATE))
            GROUP BY 1, 2, 3
            """,
            [str(source_path), start_date, start_date, end_date, end_date],
        ).fetchdf()
        lookup = connection.execute(
            """
            SELECT ua_hash, decode_status, device_type, brand, model, model_code,
                   product_family, generation, os_name, os_version, os_family,
                   api_device_type, api_brand, api_model, api_os_name, api_os_version
            FROM read_parquet(?)
            """,
            [str(lookup_path)],
        ).fetchdf()
        fast = connection.execute(
            """
            SELECT CAST(log_date AS VARCHAR) AS log_date, LOWER(TRIM(source)) AS source,
                   platform_key, platform_name, channel_name, decode_status,
                   device_type_label, brand_label, model_label, model_code_label,
                   product_family_label, generation_label, os_label, os_family_label,
                   SUM(CAST(COALESCE(raw_ts_rows, 0) AS DOUBLE)) AS raw_ts_rows
            FROM read_parquet(?)
            WHERE LOWER(TRIM(source)) = 'fast' AND log_date IS NOT NULL
              AND (? IS NULL OR CAST(log_date AS DATE) >= CAST(? AS DATE))
              AND (? IS NULL OR CAST(log_date AS DATE) <= CAST(? AS DATE))
            GROUP BY ALL
            """,
            [str(fast_path), start_date, start_date, end_date, end_date],
        ).fetchdf()
    finally:
        connection.close()

    lookup["ua_hash"] = lookup["ua_hash"].fillna("").astype(str)
    lookup = lookup[lookup["ua_hash"].ne("")].drop_duplicates("ua_hash", keep="last")
    ua_keys = source[["userAgent"]].drop_duplicates().copy()
    ua_keys["ua_norm"] = ua_keys["userAgent"].map(helpers.normalize_ua)
    ua_keys["ua_hash"] = ua_keys["ua_norm"].map(helpers.ua_hash)
    ua_keys = ua_keys.merge(lookup, on="ua_hash", how="left", validate="many_to_one")
    status = ua_keys["decode_status"].fillna("not_in_lookup").astype(str).str.lower()
    ua_keys["device"] = helpers.canonical_device_labels(
        helpers.coalesce_text(ua_keys, ["device_type", "api_device_type"])
    )
    ua_keys["model"] = helpers.granular_device_model_labels(
        helpers.coalesce_text(ua_keys, ["brand", "api_brand"]),
        helpers.coalesce_text(ua_keys, ["model", "api_model"]),
        helpers.coalesce_text(ua_keys, ["model_code"]),
        helpers.coalesce_text(ua_keys, ["product_family"]),
        helpers.coalesce_text(ua_keys, ["generation"]),
    )
    ua_keys["os"] = helpers.canonical_os_labels(
        helpers.coalesce_text(ua_keys, ["os_name", "api_os_name", "os_family"])
    )
    ua_keys["os_detail"] = helpers.granular_os_labels(
        helpers.coalesce_text(ua_keys, ["os_name", "api_os_name", "os_family"]),
        helpers.coalesce_text(ua_keys, ["os_version", "api_os_version"]),
    )
    hierarchy_columns = ["device", "model", "os", "os_detail"]
    ua_keys.loc[status.eq("malformed"), hierarchy_columns] = "Malformed / Noise"
    ua_keys.loc[status.isin({"unknown", "not_in_lookup"}), hierarchy_columns] = helpers.UNKNOWN_LABEL
    source = source.merge(
        ua_keys[["userAgent", *hierarchy_columns]], on="userAgent", how="left", validate="many_to_one"
    )
    source[hierarchy_columns] = source[hierarchy_columns].fillna(helpers.UNKNOWN_LABEL)
    source = source[source["raw_ts_rows"].gt(0)]
    source = source.groupby(
        ["log_date", "source", *hierarchy_columns], as_index=False, observed=True, dropna=False
    )["raw_ts_rows"].sum()
    source["scope"] = "source"
    source["channel"] = ""
    source["platform"] = ""

    fast_status = fast["decode_status"].fillna("").astype(str).str.lower()
    fast["device"] = helpers.canonical_device_labels(fast["device_type_label"])
    fast["model"] = helpers.granular_device_model_labels(
        fast["brand_label"], fast["model_label"], fast["model_code_label"],
        fast["product_family_label"], fast["generation_label"],
    )
    fast["os"] = helpers.canonical_os_labels(helpers.coalesce_text(fast, ["os_label", "os_family_label"]))
    fast["os_detail"] = fast["os_label"].fillna("").astype(str).str.strip().replace(
        {"": helpers.UNKNOWN_LABEL, "OS Not Exposed In UA": helpers.UNKNOWN_LABEL, "Unknown / NA": helpers.UNKNOWN_LABEL}
    )
    fast.loc[fast_status.eq("malformed"), hierarchy_columns] = "Malformed / Noise"
    fast.loc[fast_status.isin({"unknown", "not_in_lookup"}), ["model", "os_detail"]] = helpers.UNKNOWN_LABEL
    fast["channel"] = helpers.normalize_channel_names(fast["channel_name"])
    fast["platform"] = fast["platform_name"].fillna("").astype(str).str.strip()
    fast["platform"] = fast["platform"].where(
        fast["platform"].ne(""), fast["platform_key"].fillna("").astype(str).str.strip()
    ).replace("", helpers.UNKNOWN_LABEL)
    fast = fast[fast["raw_ts_rows"].gt(0)]
    fast = fast.groupby(
        ["log_date", "source", "channel", "platform", *hierarchy_columns],
        as_index=False, observed=True, dropna=False,
    )["raw_ts_rows"].sum()
    fast["scope"] = "fast_detail"

    combined = helpers.pd.concat(
        [
            source[["log_date", "source", "scope", "channel", "platform", *hierarchy_columns, "raw_ts_rows"]],
            fast[["log_date", "source", "scope", "channel", "platform", *hierarchy_columns, "raw_ts_rows"]],
        ],
        ignore_index=True,
    )
    combined["watch_hours"] = combined["raw_ts_rows"] * helpers.HOURS_PER_MEDIA_SEGMENT
    combined = combined.sort_values(
        ["log_date", "source", "scope", "channel", "platform", *hierarchy_columns]
    )
    return [
        [
            str(row.log_date), str(row.source), str(row.scope), str(row.channel), str(row.platform),
            str(row.device), str(row.model), str(row.os), str(row.os_detail), float(row.watch_hours),
        ]
        for row in combined.itertuples(index=False)
    ]


def load_asn_rows(path: Path, start_date: str | None = None, end_date: str | None = None) -> list[list[Any]]:
    """Read the canonical source/date ASN mart with decoded provider metadata."""
    missing = sorted(ASN_COLUMNS - parquet_columns(path))
    if missing:
        raise ValueError(f"ASN Parquet is missing required column(s): {', '.join(missing)}")
    connection = duckdb.connect(":memory:")
    try:
        rows = connection.execute(
            """
            SELECT CAST(log_date AS VARCHAR) AS log_date,
                   LOWER(COALESCE(NULLIF(TRIM(source), ''), 'unknown')) AS source,
                   COALESCE(NULLIF(TRIM(asn), ''), '0') AS asn,
                   COALESCE(NULLIF(TRIM(as_name), ''), 'Unknown / NA') AS as_name,
                   COALESCE(NULLIF(TRIM(as_country), ''), 'Unknown / NA') AS as_country,
                   COALESCE(TRIM(as_domain), '') AS as_domain,
                   COALESCE(NULLIF(TRIM(asn_type), ''), 'Unknown / NA') AS asn_type,
                   LOWER(COALESCE(NULLIF(TRIM(lookup_status), ''), 'unmapped')) AS lookup_status,
                   SUM(CAST(COALESCE(raw_ts_rows, 0) AS BIGINT)) AS raw_ts_rows,
                   SUM(CAST(COALESCE(approx_unique_ips, 0) AS BIGINT)) AS approx_unique_ips
            FROM read_parquet(?)
            WHERE log_date IS NOT NULL
              AND (? IS NULL OR CAST(log_date AS DATE) >= CAST(? AS DATE))
              AND (? IS NULL OR CAST(log_date AS DATE) <= CAST(? AS DATE))
            GROUP BY 1, 2, 3, 4, 5, 6, 7, 8
            ORDER BY 1, 2, 3
            """,
            [str(path), start_date, start_date, end_date, end_date],
        ).fetchall()
    finally:
        connection.close()
    return [
        [
            str(log_date), str(source), str(asn), str(name), str(country), str(domain),
            str(network_type), str(status), int(raw_rows or 0), int(ip_activity or 0),
        ]
        for log_date, source, asn, name, country, domain, network_type, status, raw_rows, ip_activity in rows
    ]


def render_html(
    rows: list[list[Any]],
    platform_rows: list[list[Any]],
    identity_rows: list[list[Any]],
    concurrency_rows: list[list[Any]],
    ua_rows: list[list[Any]],
    ua_hierarchy_rows: list[list[Any]],
    asn_rows: list[list[Any]],
) -> str:
    payload = json.dumps(rows, ensure_ascii=True, separators=(",", ":"))
    platform_payload = json.dumps(platform_rows, ensure_ascii=True, separators=(",", ":"))
    identity_payload = json.dumps(identity_rows, ensure_ascii=True, separators=(",", ":"))
    concurrency_payload = json.dumps(concurrency_rows, ensure_ascii=True, separators=(",", ":"))
    ua_payload = json.dumps(ua_rows, ensure_ascii=True, separators=(",", ":"))
    ua_hierarchy_payload = json.dumps(ua_hierarchy_rows, ensure_ascii=True, separators=(",", ":"))
    asn_payload = json.dumps(asn_rows, ensure_ascii=True, separators=(",", ":"))
    return rf"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Watch Hours</title>
<style>
*{{box-sizing:border-box}}
:root{{--canvas:#f4f5f7;--surface:#ffffff;--ink:#17202b;--muted:#66717d;--line:#d7dde3;--accent:#b85c38;--accent-dark:#7b3520;--shadow:0 2px 8px rgba(28,38,48,.08)}}
html{{background:var(--canvas)}}
body{{margin:0;background:var(--canvas);color:var(--ink);font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;font-size:14px;line-height:1.4}}
.filter-shell{{position:sticky;top:0;z-index:30;background:rgba(244,245,247,.98);border-bottom:1px solid var(--line);box-shadow:0 2px 8px rgba(28,38,48,.06);padding:8px 12px}}
.filter-bar{{display:flex;flex-wrap:wrap;align-items:end;gap:6px 8px}}
.filter-field{{display:grid;gap:4px;min-width:0;flex:0 0 auto}}
.filter-field label{{font-size:10.5px;font-weight:800;letter-spacing:.03em;text-transform:uppercase;color:#536277}}
.date-label{{display:flex;align-items:center;gap:5px;white-space:nowrap}}
.filter-field.source{{width:102px}}.filter-field.date{{width:360px}}.filter-field.multi{{width:170px}}.filter-field.platform{{width:170px}}.filter-field.state{{width:170px}}.filter-field[hidden]{{display:none}}
select,input[type=date],.multi-toggle{{width:100%;height:30px;border:1px solid #c5cdd5;border-radius:4px;background:var(--surface);color:var(--ink);font:inherit;font-size:12px;font-weight:650;padding:5px 7px;outline:none}}
select:focus,input[type=date]:focus,.multi-toggle:focus-visible{{border-color:var(--accent);box-shadow:0 0 0 3px rgba(184,92,56,.14)}}
.date-pair{{display:flex;align-items:center;gap:4px}}.date-pair input{{width:108px;min-width:108px}}.date-preset{{width:92px;height:30px;padding:5px 6px}}
.multi-picker{{position:relative}}.multi-toggle{{display:flex;align-items:center;justify-content:space-between;gap:8px;text-align:left;cursor:pointer}}.multi-toggle:hover{{border-color:#91a5b7}}.multi-toggle .caret{{color:var(--muted);font-size:11px}}
.multi-menu{{display:none;position:absolute;top:calc(100% + 6px);left:0;width:100%;min-width:260px;max-height:min(400px,calc(100vh - 100px));overflow:hidden;z-index:40;border:1px solid #bdcbd8;border-radius:6px;background:#fff;box-shadow:var(--shadow);padding:7px}}.multi-menu.open{{display:flex;flex-direction:column}}
.picker-search{{height:30px;border:1px solid #c5cdd5;border-radius:4px;padding:5px 7px;font:inherit;font-size:12px;outline:none}}.picker-search:focus{{border-color:var(--accent);box-shadow:0 0 0 3px rgba(184,92,56,.14)}}
.picker-actions{{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:7px 1px 6px;border-bottom:1px solid #e3e9ef;color:var(--muted);font-size:11px;font-weight:700}}.text-button{{border:0;background:transparent;color:var(--accent-dark);font:inherit;font-size:11px;font-weight:850;cursor:pointer;padding:2px}}
.option-list{{overflow:auto;padding-top:4px;overscroll-behavior:contain}}.option{{display:flex;align-items:center;gap:8px;padding:7px 5px;border-radius:4px;color:#263348;font-size:12px;font-weight:650;cursor:pointer}}.option:hover{{background:#fff5f0}}.option input{{accent-color:var(--accent);margin:0}}.option[hidden]{{display:none}}
.summary-layout{{display:grid;grid-template-columns:minmax(180px,12.5%) minmax(0,1fr);gap:14px;align-items:start;width:100%;max-width:none}}.summary-layout[hidden],.stream-matrix-row[hidden]{{display:none}}.summary-layout>section,.summary-layout>.chart-pair{{min-width:0;align-self:start}}main{{max-width:none;margin:0;padding:14px 12px 0}}
.stream-matrix{{display:grid;grid-template-columns:1fr;gap:10px;width:100%;max-width:none}}.stream-matrix[hidden]{{display:none}}.stream-matrix-row{{display:grid;grid-template-columns:minmax(180px,20%) minmax(0,1fr);gap:14px;align-items:stretch;min-width:0}}.stream-matrix-row>.chart-section,.stream-matrix-row>.chart-section.compact{{height:280px}}.matrix-detail{{min-width:0;height:280px;border:1px solid #d8e1ee;border-radius:5px;background:#fff;overflow:hidden}}.matrix-detail-title{{padding:8px 10px;border-bottom:1px solid #e2e8f0;color:#334155;font-size:11px;font-weight:800}}.matrix-detail-scroll{{height:243px;overflow-y:scroll;overscroll-behavior:contain;scroll-behavior:auto}}.matrix-detail table{{width:100%;border-collapse:collapse;table-layout:fixed;font-size:10px;font-variant-numeric:tabular-nums}}.matrix-detail th,.matrix-detail td{{height:27px;box-sizing:border-box;padding:5px 7px;border-bottom:1px solid #edf2f7;white-space:nowrap}}.matrix-detail th{{position:sticky;top:0;height:27px;background:#f8fafc;color:#64748b;text-align:left;font-size:9px;font-weight:800;text-transform:uppercase;z-index:1}}.matrix-detail td{{color:#334155}}.matrix-detail th:nth-child(n+2),.matrix-detail td:nth-child(n+2){{text-align:right}}.matrix-detail tr:last-child td{{border-bottom:0}}
.kpi{{width:100%;max-width:none;box-sizing:border-box;border:1px solid var(--line);border-left:3px solid var(--accent);border-radius:5px;background:var(--surface);box-shadow:var(--shadow);padding:12px 16px}}.kpi.secondary{{margin-top:8px;padding:9px 12px;border-left-color:#7b8794}}.kpi-label{{color:#5f6974;font-size:11px;font-weight:800;letter-spacing:.04em;text-transform:uppercase}}.kpi.secondary .kpi-label{{font-size:10px}}.kpi-value{{display:block;margin-top:5px;font-size:40px;font-weight:780;letter-spacing:0;line-height:1;color:#17202b;font-variant-numeric:tabular-nums;white-space:nowrap}}.kpi.secondary .kpi-value{{margin-top:3px;font-size:24px}}
.summary-rail{{min-width:0;display:flex;flex-direction:column;align-self:start}}.summary-rail.bounded{{height:480px;max-height:480px;overflow:hidden}}.summary-rail.bounded .daily-detail{{display:flex;flex-direction:column;flex:1;min-height:0}}.summary-rail.bounded .daily-detail-scroll{{height:432px;max-height:432px;flex:none;overflow-y:scroll;overscroll-behavior:contain;scroll-behavior:auto}}
.daily-detail{{margin-top:10px;border:1px solid #d8e1ee;border-radius:5px;background:#fff;overflow:hidden}}.daily-detail-title{{padding:8px 10px;border-bottom:1px solid #e2e8f0;color:#334155;font-size:11px;font-weight:800}}.daily-detail-scroll{{max-height:calc(100vh - 270px);overflow-y:auto}}.daily-detail table{{width:100%;border-collapse:collapse;table-layout:fixed;font-size:10px;font-variant-numeric:tabular-nums}}.daily-detail th,.daily-detail td{{height:27px;box-sizing:border-box;padding:5px 7px;border-bottom:1px solid #edf2f7;white-space:nowrap}}.daily-detail th{{position:sticky;top:0;height:27px;background:#f8fafc;color:#64748b;text-align:left;font-size:9px;font-weight:800;text-transform:uppercase;z-index:1}}.daily-detail tbody tr{{height:27px}}.daily-detail td{{color:#334155}}.daily-detail th:nth-child(n+2),.daily-detail td:nth-child(n+2){{text-align:right}}.daily-detail tr:last-child td{{border-bottom:0}}
.chart-pair{{display:grid;grid-template-columns:1fr;gap:10px;max-width:100%;min-width:0}}.chart-section{{margin-top:0;width:100%;max-width:100%;box-sizing:border-box;border:1px solid #e2e8f0;border-radius:7px;background:#fff;box-shadow:0 1px 2px rgba(15,23,42,.05);padding:10px 12px 7px;min-width:0;overflow:hidden}}.chart-section.compact{{padding-top:8px;padding-bottom:5px}}.chart-title{{display:flex;align-items:baseline;justify-content:flex-start;flex-wrap:wrap;gap:8px;margin:0 0 5px;color:#172033;font-size:13px;font-weight:800;line-height:1.2}}.chart-total{{color:#334155;font-size:12px;font-weight:800;font-variant-numeric:tabular-nums;white-space:nowrap}}.chart-wrap{{display:flex;width:100%;max-width:100%;overflow:hidden;height:280px}}.chart-y-axis{{position:relative;flex:0 0 70px;height:280px;background:#fff;border-right:1px solid #cbd5e1;z-index:2}}.chart-y-axis-label{{position:absolute;right:8px;transform:translateY(-50%);color:#64748b;font-size:10px;font-variant-numeric:tabular-nums;white-space:nowrap}}.chart-scroll{{min-width:0;flex:1;overflow-x:auto;overflow-y:hidden}}.daily-chart{{display:block;width:auto;min-width:0;height:280px}}.chart-section.compact .chart-wrap,.chart-section.compact .chart-y-axis,.chart-section.compact .chart-scroll{{height:220px}}.chart-section.compact .daily-chart{{height:220px}}.chart-grid{{stroke:#e2e8f0;stroke-width:1}}.chart-axis{{stroke:#cbd5e1;stroke-width:1}}.chart-x-label{{fill:#64748b;font-size:10px;font-variant-numeric:tabular-nums;text-anchor:middle;font-weight:750}}.chart-bar{{opacity:.95}}.chart-value-label{{fill:#172033;font-size:10px;font-weight:850;text-anchor:middle}}.chart-empty{{fill:#64748b;font-size:12px}}
.loading-overlay{{position:fixed;inset:0;z-index:50;display:flex;align-items:center;justify-content:center;gap:9px;background:rgba(245,247,249,.58);opacity:0;pointer-events:none;transition:opacity .12s ease}}.loading-overlay.active{{opacity:1;pointer-events:auto}}.loading-message{{display:flex;align-items:center;gap:8px;border:1px solid #c9d8df;border-radius:5px;background:#fff;box-shadow:var(--shadow);padding:8px 10px;color:var(--accent-dark);font-size:12px;font-weight:750}}.loading-mark{{width:8px;height:8px;border-radius:50%;background:var(--accent)}}
.stream-matrix-row>.chart-section,.stream-matrix-row>.chart-section.compact{{height:285px;padding:8px 10px 4px}}.stream-matrix-row>.matrix-detail{{height:285px}}.stream-matrix-row .matrix-detail-scroll{{height:248px}}.stream-matrix-row{{grid-template-columns:minmax(180px,10%) minmax(0,1fr)}}.stream-matrix-row>.chart-section{{overflow:hidden}}.stream-matrix-row .chart-wrap{{height:220px;overflow:hidden}}.stream-matrix-row .chart-y-axis,.stream-matrix-row .chart-scroll{{height:220px!important}}.stream-matrix-row .daily-chart{{height:220px}}.stream-matrix-row .chart-section.compact .chart-wrap,.stream-matrix-row .chart-section.compact .chart-y-axis,.stream-matrix-row .chart-section.compact .chart-scroll{{height:200px!important}}.stream-matrix-row .chart-section.compact .daily-chart{{height:200px}}.stream-matrix-row>.concurrency-section{{height:320px}}.stream-matrix-row .concurrency-section .chart-wrap{{height:278px!important}}.stream-matrix-row .concurrency-section .chart-y-axis{{height:255px!important}}.stream-matrix-row .concurrency-section .chart-scroll{{height:278px!important}}.stream-matrix-row .concurrency-section .concurrency-chart{{height:255px!important}}
@media(max-width:820px){{.filter-shell{{padding:8px 10px}}main{{padding:12px 10px 0}}.summary-layout{{grid-template-columns:1fr}}.chart-section{{margin-top:0}}}}
@media(max-width:520px){{.filter-field.source{{width:102px}}.filter-field.date{{width:350px}}.filter-field.multi{{width:160px}}.date-pair input{{width:103px;min-width:103px}}.date-preset{{width:86px}}.kpi{{padding:18px}}.kpi-value{{font-size:32px}}}}
.stream-matrix .chart-total{{color:#0f766e;font-weight:850}}
.stream-matrix-row .chart-scroll{{overflow-x:auto!important;overflow-y:hidden!important}}
.concurrency-title{{display:flex;align-items:center;justify-content:space-between;gap:6px}}.concurrency-resolution{{flex:0 0 auto;width:62px;height:21px;margin:0;border:1px solid #b9c5d1;border-radius:4px;background:#fff;color:#334155;padding:1px 4px;font:inherit;font-size:9px;font-weight:800;outline:none;cursor:pointer}}.concurrency-resolution:hover,.concurrency-resolution:focus{{border-color:#1f7897;box-shadow:0 0 0 2px rgba(31,120,151,.1)}}.concurrency-chart{{height:240px!important}}.concurrency-line{{fill:none;stroke:#1f7897;stroke-width:2.35;stroke-linecap:round;stroke-linejoin:round;vector-effect:non-scaling-stroke}}.concurrency-day-line{{stroke:#cbd5e1;stroke-width:1;stroke-dasharray:3 4}}.concurrency-day-label{{fill:#334155;font-size:11px;font-weight:850;text-anchor:middle}}.concurrency-hover-line{{stroke:#475569;stroke-width:1;stroke-dasharray:3 3;pointer-events:none}}.concurrency-hover-dot{{fill:#fff;stroke:#1f7897;stroke-width:2.4;pointer-events:none}}.concurrency-hit-area{{fill:transparent;cursor:crosshair}}
.chart-subtitle{{display:block;margin-top:1px;color:#667085;font-size:10px;font-weight:650;line-height:1.1}}.concurrency-note{{display:none}}
.concurrency-scroll{{position:relative;overflow-x:hidden!important;scrollbar-gutter:auto}}.concurrency-legend{{display:flex;align-items:center;gap:5px 12px;min-height:20px;margin:0 0 2px 70px;overflow-x:auto;color:#475569;font-size:9px;font-weight:750;white-space:nowrap}}.concurrency-legend-item{{display:inline-flex;align-items:center;gap:4px}}.concurrency-legend-swatch{{width:14px;height:3px;border-radius:2px}}.concurrency-tooltip{{position:fixed;z-index:100;display:none;min-width:205px;max-width:320px;padding:9px 11px;border:1px solid rgba(255,255,255,.16);border-radius:5px;background:rgba(28,32,36,.96);box-shadow:0 8px 24px rgba(15,23,42,.28);color:#fff;font-size:11px;line-height:1.4;pointer-events:none;white-space:nowrap}}.concurrency-tooltip strong{{display:block;margin-bottom:4px;font-size:12px}}.concurrency-tooltip .tooltip-value{{font-size:11px;font-weight:750}}.concurrency-tooltip .tooltip-value span{{display:inline-block;width:8px;height:8px;margin-right:6px;border-radius:50%}}.concurrency-tooltip .tooltip-change{{margin-top:3px;color:#d7e3ec}}
.chart-action{{margin-left:auto;height:25px;border:1px solid #b8c6d4;border-radius:4px;background:#fff;color:#334155;padding:3px 9px;font:inherit;font-size:10px;font-weight:800;cursor:pointer}}.chart-action:hover{{border-color:#1f7897;color:#1f7897;background:#f5fbfd}}.concurrency-section.expanded{{position:fixed;inset:8px;z-index:90;height:auto!important;padding:12px 14px!important;overflow:hidden!important;box-shadow:0 18px 55px rgba(15,23,42,.28)}}.concurrency-section.expanded .chart-wrap{{height:calc(100vh - 92px)!important}}.concurrency-section.expanded .chart-y-axis,.concurrency-section.expanded .chart-scroll{{height:calc(100vh - 92px)!important}}.concurrency-section.expanded .concurrency-chart{{height:calc(100vh - 116px)!important}}body.chart-expanded{{overflow:hidden}}
.device-os-section{{margin-top:10px;min-width:0}}.device-os-header{{display:flex;align-items:baseline;gap:10px;margin-bottom:6px}}.device-os-header h2{{margin:0;color:#172033;font-size:14px;line-height:1.2}}.device-os-status{{color:#64748b;font-size:10px;font-weight:700}}.device-book{{width:min(820px,100%);border:1px solid #d8e1ee;border-radius:6px;background:#fff;overflow:hidden;box-shadow:0 1px 2px rgba(15,23,42,.04)}}.device-book-nav{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));border-bottom:1px solid #dbe3eb;background:#f8fafc}}.device-book-step{{position:relative;min-width:0;height:42px;border:0;border-right:1px solid #e2e8f0;background:transparent;color:#64748b;padding:5px 10px;text-align:left;font:inherit;cursor:pointer}}.device-book-step:last-child{{border-right:0}}.device-book-step strong{{display:block;overflow:hidden;color:inherit;font-size:10px;font-weight:850;text-overflow:ellipsis;white-space:nowrap}}.device-book-step span{{display:block;margin-bottom:1px;font-size:8px;font-weight:800;text-transform:uppercase}}.device-book-step.active{{background:#fff;color:#176b87}}.device-book-step.active::after{{position:absolute;right:8px;bottom:-1px;left:8px;height:2px;background:#218b83;content:""}}.device-book-step:disabled{{cursor:default;opacity:.42}}.device-book-breadcrumb{{height:31px;padding:7px 10px;border-bottom:1px solid #e2e8f0;background:#fff;color:#64748b;font-size:9px;font-weight:750;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}.device-book-breadcrumb strong{{color:#176b87}}.device-os-panel{{min-width:0;background:#fff;overflow:hidden}}.device-os-panel header{{display:flex;align-items:center;justify-content:space-between;gap:8px;height:36px;padding:7px 10px;border-bottom:1px solid #e2e8f0;color:#334155;font-size:11px;font-weight:850}}.device-os-count{{color:#64748b;font-size:9px;font-weight:750;white-space:nowrap}}.device-os-list{{height:306px;overflow-y:auto;overscroll-behavior:contain;scrollbar-gutter:stable}}.ua-row{{display:grid;width:100%;grid-template-columns:25px minmax(0,1fr) auto 12px;align-items:center;gap:6px;min-height:34px;padding:5px 9px;border:0;border-bottom:1px solid #edf2f7;background:#fff;color:inherit;font:inherit;font-size:10px;text-align:left;cursor:pointer}}.ua-row:hover,.ua-row.selected{{background:#f0fdfa}}.ua-row:focus-visible{{position:relative;outline:2px solid #218b83;outline-offset:-2px}}.ua-rank{{color:#94a3b8;font-weight:750}}.ua-main{{min-width:0}}.ua-name{{overflow:hidden;color:#334155;font-weight:750;text-overflow:ellipsis;white-space:nowrap}}.ua-track{{height:3px;margin-top:4px;border-radius:2px;background:#edf2f7;overflow:hidden}}.ua-fill{{height:100%;border-radius:2px;background:#2f9389}}.ua-value{{color:#172033;font-weight:800;text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}}.ua-share{{display:block;color:#64748b;font-size:9px;font-weight:650}}.ua-drill{{color:#94a3b8;font-size:11px;font-weight:900}}.ua-empty{{display:flex;align-items:center;justify-content:center;height:100%;padding:20px;color:#64748b;font-size:11px;text-align:center}}.device-book-footer{{display:grid;grid-template-columns:auto 1fr auto auto;align-items:center;gap:8px;height:36px;padding:5px 8px;border-top:1px solid #e2e8f0;background:#f8fafc}}.device-book-position{{color:#64748b;font-size:9px;font-weight:750;text-align:center}}.device-book-action{{height:25px;border:1px solid #bdc9d5;border-radius:4px;background:#fff;color:#334155;padding:3px 9px;font:inherit;font-size:9px;font-weight:800;cursor:pointer}}.device-book-action:hover:not(:disabled){{border-color:#218b83;color:#176b87}}.device-book-action:disabled{{cursor:default;opacity:.4}}
.evidence-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:10px;min-width:0}}.evidence-grid[hidden]{{display:none}}.evidence-grid .device-os-section,.networks-section{{min-width:0;margin-top:0}}.evidence-grid .device-book,.network-book{{width:100%;height:451px;border:1px solid #d8e1ee;border-radius:6px;background:#fff;overflow:hidden;box-shadow:0 1px 2px rgba(15,23,42,.04)}}.network-controls{{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:8px;height:42px;padding:5px 8px;border-bottom:1px solid #dbe3eb;background:#f8fafc}}.network-controls input{{min-width:0;width:100%;height:30px;border:1px solid #c5cdd5;border-radius:4px;background:#fff;color:#17202b;padding:5px 7px;font:inherit;font-size:10px;outline:none}}.network-controls input:focus{{border-color:#218b83;box-shadow:0 0 0 2px rgba(33,139,131,.12)}}.network-modes{{display:flex;align-items:center;gap:2px}}.network-modes button{{height:26px;border:1px solid #c5cdd5;background:#fff;color:#64748b;padding:3px 7px;font:inherit;font-size:9px;font-weight:800;cursor:pointer}}.network-modes button:first-child{{border-radius:4px 0 0 4px}}.network-modes button:last-child{{border-radius:0 4px 4px 0}}.network-modes button.active{{border-color:#218b83;background:#e9f8f5;color:#176b87}}.network-summary{{display:flex;align-items:center;justify-content:space-between;gap:8px;height:31px;padding:7px 10px;border-bottom:1px solid #e2e8f0;color:#64748b;font-size:9px;font-weight:750;white-space:nowrap}}.network-summary strong{{color:#176b87}}.network-list{{height:306px}}.network-row{{display:grid;grid-template-columns:25px minmax(0,1fr) minmax(146px,auto);align-items:center;gap:8px;min-height:58px;padding:6px 9px;border-bottom:1px solid #edf2f7;font-size:10px}}.network-main{{min-width:0}}.network-name{{overflow:hidden;color:#334155;font-weight:800;text-overflow:ellipsis;white-space:nowrap}}.network-meta{{overflow:hidden;margin-top:1px;color:#64748b;font-size:9px;text-overflow:ellipsis;white-space:nowrap}}.network-value{{color:#172033;text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}}.network-value strong{{display:block;font-size:11px;font-weight:850}}.network-value strong small{{color:#475569;font-size:8px;font-weight:750}}.network-value span{{display:block;color:#64748b;font-size:8.5px;font-weight:650}}.network-value .network-share{{color:#176b87;font-weight:800}}.network-footer{{display:flex;align-items:center;justify-content:space-between;gap:8px;height:36px;padding:5px 9px;border-top:1px solid #e2e8f0;background:#f8fafc;color:#64748b;font-size:9px;font-weight:750}}.network-footer span:first-child{{color:#176b87;font-weight:850}}
@media(max-width:620px){{.device-book-nav{{grid-template-columns:repeat(2,minmax(0,1fr))}}.device-book-step:nth-child(-n+2){{border-bottom:1px solid #e2e8f0}}}}
@media(max-width:980px){{.evidence-grid{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<div class="loading-overlay" id="loadingOverlay" aria-hidden="true"><div class="loading-message"><span class="loading-mark"></span>Updating filters</div></div>
<header class="filter-shell" aria-label="Dashboard filters">
  <div class="filter-bar">
    <div class="filter-field source"><label for="sourceFilter">Source</label><select id="sourceFilter"></select></div>
    <div class="filter-field date"><label class="date-label" for="dateFrom">Date range</label><div class="date-pair"><input id="dateFrom" type="date"><span class="date-separator">to</span><input id="dateTo" type="date"><select id="datePreset" class="date-preset" aria-label="Date range preset"><option value="yesterday">Yesterday</option><option value="7">7D</option><option value="15">15D</option><option value="30">30D</option><option value="all">All</option><option value="custom">Custom</option></select></div></div>
    <div class="filter-field multi"><label>Channel</label><div class="multi-picker" id="channelPicker"></div></div>
    <div class="filter-field multi platform" id="platformField"><label>Platform</label><div class="multi-picker" id="platformPicker"></div></div>
    <div class="filter-field multi"><label>Region</label><div class="multi-picker" id="regionPicker"></div></div>
    <div class="filter-field multi state"><label>State</label><div class="multi-picker" id="statePicker"></div></div>
  </div>
</header>
<main>
  <div class="summary-layout" id="defaultLayout" hidden>
    <section class="summary-rail" id="summaryRail" aria-label="Daily detail summary">
      <div class="daily-detail" aria-label="Daily detail"><div class="daily-detail-title">Daily Detail</div><div class="daily-detail-scroll" id="dailyDetailScroll"><table><thead><tr><th>Date</th><th>Watch Hrs</th><th>Viewers</th></tr></thead><tbody id="dailyDetailBody"></tbody></table></div></div>
    </section>
    <div class="chart-pair">
      <section class="chart-section" aria-label="Daily watch hours">
        <h2 class="chart-title"><span>Daily Watch Hours</span><span class="chart-total" id="watchHoursHeadingValue">Total Watch Hours: 0</span></h2>
        <div class="chart-wrap"><div class="chart-y-axis" id="dailyChartYAxis" aria-hidden="true"></div><div class="chart-scroll"><svg class="daily-chart" id="dailyChart" viewBox="0 0 1200 360" role="img" aria-label="Daily watch hours bar chart"></svg></div></div>
      </section>
      <section class="chart-section" aria-label="Daily viewers">
        <h2 class="chart-title"><span>Daily Total Viewers</span><span class="chart-total" id="viewersHeadingValue">Total Viewers: 0</span></h2>
        <div class="chart-wrap"><div class="chart-y-axis" id="viewerChartYAxis" aria-hidden="true"></div><div class="chart-scroll"><svg class="daily-chart" id="viewerChart" viewBox="0 0 1200 360" role="img" aria-label="Daily total viewers bar chart"></svg></div></div>
      </section>
      <section class="chart-section" id="identitySection" aria-label="Daily device and session identifiers" hidden>
        <h2 class="chart-title"><span>Daily Device / Session IDs</span><span class="chart-total" id="identityStatus">STREAM identity telemetry</span></h2>
        <div class="chart-wrap"><div class="chart-y-axis" id="identityChartYAxis" aria-hidden="true"></div><div class="chart-scroll"><svg class="daily-chart" id="identityChart" viewBox="0 0 1200 360" role="img" aria-label="Daily device and session ID counts"></svg></div></div>
      </section>
    </div>
  </div>
  <div class="stream-matrix" id="streamMatrix" hidden>
    <div class="stream-matrix-row">
      <section class="matrix-detail" aria-label="Daily watch hours detail"><div class="matrix-detail-title">Daily Watch Hours</div><div class="matrix-detail-scroll" id="streamWatchDetailScroll"><table><thead><tr><th>Date</th><th>Watch Hrs</th></tr></thead><tbody id="streamWatchDetailBody"></tbody></table></div></section>
      <section class="chart-section" aria-label="Daily watch hours"><h2 class="chart-title"><span>Daily Watch Hours</span><span class="chart-total" id="streamWatchTotal">Total Watch Hours: 0</span></h2><div class="chart-wrap"><div class="chart-y-axis" id="streamWatchChartYAxis" aria-hidden="true"></div><div class="chart-scroll"><svg class="daily-chart" id="streamWatchChart" viewBox="0 0 1200 360" role="img" aria-label="Daily watch hours bar chart"></svg></div></div></section>
    </div>
    <div class="stream-matrix-row">
      <section class="matrix-detail" aria-label="Daily viewers detail"><div class="matrix-detail-title">Daily Viewers</div><div class="matrix-detail-scroll" id="streamViewerDetailScroll"><table><thead><tr><th>Date</th><th>Viewers</th></tr></thead><tbody id="streamViewerDetailBody"></tbody></table></div></section>
      <section class="chart-section" aria-label="Daily viewers"><h2 class="chart-title"><span>Daily Total Viewers</span><span class="chart-total" id="streamViewerTotal">Total Viewers: 0</span></h2><div class="chart-wrap"><div class="chart-y-axis" id="streamViewerChartYAxis" aria-hidden="true"></div><div class="chart-scroll"><svg class="daily-chart" id="streamViewerChart" viewBox="0 0 1200 360" role="img" aria-label="Daily total viewers bar chart"></svg></div></div></section>
    </div>
    <div class="stream-matrix-row" id="streamIdentityRow">
      <section class="matrix-detail" aria-label="Daily device and session detail"><div class="matrix-detail-title">Daily Device / Session IDs</div><div class="matrix-detail-scroll" id="streamIdentityDetailScroll"><table><thead><tr><th>Date</th><th>Devices</th><th>Sessions</th></tr></thead><tbody id="streamIdentityDetailBody"></tbody></table></div></section>
      <section class="chart-section" id="streamIdentitySection" aria-label="Daily device and session identifiers"><h2 class="chart-title"><span>Daily Device / Session IDs</span><span class="chart-total">STREAM identity telemetry</span></h2><div class="chart-wrap"><div class="chart-y-axis" id="streamIdentityChartYAxis" aria-hidden="true"></div><div class="chart-scroll"><svg class="daily-chart" id="streamIdentityChart" viewBox="0 0 1200 360" role="img" aria-label="Daily device and session ID counts"></svg></div></div></section>
    </div>
    <div class="stream-matrix-row" id="concurrencyRow">
      <section class="matrix-detail" aria-label="Daily concurrency detail"><div class="matrix-detail-title concurrency-title"><span>Concurrency</span><select id="concurrencyResolution" class="concurrency-resolution" aria-label="Concurrency interval"><option value="1">1 min</option><option value="5">5 min</option></select></div><div class="matrix-detail-scroll" id="concurrencyDetailScroll"><table><thead><tr><th>Date</th><th title="Active viewer minute sum">Sum</th><th title="Peak active users">Peak</th></tr></thead><tbody id="concurrencyDetailBody"></tbody></table></div></section>
      <section class="chart-section concurrency-section" id="concurrencySection" aria-label="Concurrency line chart"><h2 class="chart-title"><span>Active Viewer Minute Sum<small class="chart-subtitle">cliIP counts summed inside selected interval</small></span><span class="chart-total" id="concurrencyTotal">Peak Users: 0</span><button type="button" class="chart-action" id="concurrencyExpand" aria-expanded="false">Expand</button></h2><div class="concurrency-legend" id="concurrencyLegend" aria-label="Date color legend"></div><div class="chart-wrap"><div class="chart-y-axis" id="concurrencyChartYAxis" aria-hidden="true"></div><div class="chart-scroll concurrency-scroll"><svg class="daily-chart concurrency-chart" id="concurrencyChart" viewBox="0 0 1200 360" role="img" aria-label="Minute-level cliIP concurrency line chart"></svg><div class="concurrency-tooltip" id="concurrencyTooltip"></div></div></div><div class="concurrency-note" id="concurrencyNote"></div></section>
    </div>
  </div>
  <div class="evidence-grid" id="evidenceGrid" hidden>
  <section class="device-os-section" id="deviceOsSection" aria-label="Devices and operating systems">
    <div class="device-os-header"><h2>Devices &amp; Operating Systems</h2><span class="device-os-status" id="deviceOsStatus"></span></div>
    <div class="device-book" id="deviceBook">
      <nav class="device-book-nav" aria-label="Device and OS levels">
        <button type="button" class="device-book-step active" data-ua-level="0"><span>Level 1</span><strong>Device Type</strong></button>
        <button type="button" class="device-book-step" data-ua-level="1"><span>Level 2</span><strong>Device Model</strong></button>
        <button type="button" class="device-book-step" data-ua-level="2"><span>Level 3</span><strong>Operating System</strong></button>
        <button type="button" class="device-book-step" data-ua-level="3"><span>Level 4</span><strong>OS Version</strong></button>
      </nav>
      <div class="device-book-breadcrumb" id="uaBreadcrumb" aria-label="Current device hierarchy">All devices</div>
      <article class="device-os-panel"><header><span id="uaHierarchyTitle">Device Types</span><span class="device-os-count" id="uaHierarchyCount"></span></header><div class="device-os-list" id="uaHierarchyList"></div></article>
      <div class="device-book-footer"><button type="button" class="device-book-action" id="deviceBookPrevious">Previous</button><span class="device-book-position" id="deviceBookPosition">1 of 4</span><button type="button" class="device-book-action" id="deviceBookReset">Reset</button><button type="button" class="device-book-action" id="deviceBookNext">Next</button></div>
    </div>
  </section>
  <section class="networks-section" id="networksSection" aria-label="Internet providers and networks">
    <div class="device-os-header"><h2>Internet Providers &amp; Networks</h2><span class="device-os-status" id="networkStatus"></span></div>
    <div class="network-book">
      <div class="network-controls"><input id="networkSearch" type="search" placeholder="Search ASN, provider, domain, country, or type" aria-label="Search networks and ASNs"><div class="network-modes" id="networkModes" aria-label="Network decode status"><button type="button" class="active" data-network-mode="all">All</button><button type="button" data-network-mode="decoded">Decoded</button><button type="button" data-network-mode="unresolved">Unresolved</button></div></div>
      <div class="network-summary"><span id="networkCoverage">Decoded coverage: 0%</span><span id="networkCounts">0 decoded | 0 unresolved</span></div>
      <article class="device-os-panel"><header><span>Provider Ranking by Watch Hours</span><span class="device-os-count" id="networkCount"></span></header><div class="device-os-list network-list" id="networkList"></div></article>
      <div class="network-footer"><span id="networkWatchHours">Selected Total: 0 watch hrs</span><span id="networkActivityHelp">Active IPs are network addresses, not people</span></div>
    </div>
  </section>
  </div>
</main>
<script>
const rows={payload};
const platformRows={platform_payload};
const identityRows={identity_payload};
const concurrencyRows={concurrency_payload};
const uaRows={ua_payload};
const uaHierarchyRows={ua_hierarchy_payload};
const asnRows={asn_payload};
const state={{source:'fast',from:'',to:'',channels:new Set(),regions:new Set(),states:new Set(),platforms:new Set()}};
const byId=id=>document.getElementById(id);
const unique=(index)=>[...new Set(rows.map(row=>row[index]))].sort((a,b)=>a.localeCompare(b));
const allSources=['fast','stream'].filter(source=>rows.some(row=>row[1]===source)),allRegions=unique(2),allStates=unique(3);
const allPlatforms=[...new Set(platformRows.map(row=>row[7]))].sort((a,b)=>a.localeCompare(b));
const channelsForSource=source=>[...new Set(rows.filter(row=>row[1]===source).map(row=>row[4]))].sort((a,b)=>a.localeCompare(b));
const formatHours=new Intl.NumberFormat('en-IN',{{maximumFractionDigits:0}});
const formatNumber=new Intl.NumberFormat('en-IN');
const formatAxis=value=>value>=1000000?`${{(value/1000000).toFixed(value%1000000?1:0)}}M`:value>=1000?`${{(value/1000).toFixed(value%1000?0:0)}}K`:String(Math.round(value));
const regionNames=typeof Intl.DisplayNames==='function'?new Intl.DisplayNames(['en'],{{type:'region'}}):null;
let renderToken=0;
function selectedText(label,selected,total){{return !selected.size||selected.size===total?`All ${{label.toLowerCase()}}`:`${{selected.size}} selected`}}
function regionLabel(value){{if(value==='Unknown / NA'||!regionNames)return value;try{{const name=regionNames.of(value);return name&&name!==value?`${{value}} - ${{name}}`:value}}catch(error){{return value}}}}
function buildSource(){{const select=byId('sourceFilter');select.innerHTML=allSources.map(value=>`<option value="${{escapeHtml(value)}}">${{escapeHtml(value.toUpperCase())}}</option>`).join('');if(!allSources.includes(state.source))state.source=allSources[0]||'';select.value=state.source;select.addEventListener('change',()=>{{state.source=select.value;state.channels.clear();state.platforms.clear();buildChannelPicker();scheduleRender()}})}}
function buildChannelPicker(){{buildPicker('channelPicker','Channels',channelsForSource(state.source),'channels')}}
function buildPicker(id,label,values,key){{const root=byId(id);root.innerHTML=`<button type="button" class="multi-toggle" aria-expanded="false"><span data-label></span><span class="caret">v</span></button><div class="multi-menu"><input class="picker-search" type="search" placeholder="Search ${{label.toLowerCase()}}s..." autocomplete="off"><div class="picker-actions"><span data-status></span><button class="text-button" type="button">Clear</button></div><div class="option-list">${{values.map(value=>{{const text=label==='Regions'?regionLabel(value):value;return `<label class="option" data-value="${{escapeHtml(value)}}" data-search="${{escapeHtml((value+' '+text).toLocaleLowerCase())}}"><input type="checkbox" value="${{escapeHtml(value)}}"><span>${{escapeHtml(text)}}</span></label>`}}).join('')}}</div></div>`;
  const toggle=root.querySelector('.multi-toggle'),menu=root.querySelector('.multi-menu'),search=root.querySelector('.picker-search'),clear=root.querySelector('.text-button');
  toggle.addEventListener('click',event=>{{event.stopPropagation();document.querySelectorAll('.multi-menu.open').forEach(node=>{{if(node!==menu)node.classList.remove('open')}});const open=!menu.classList.contains('open');menu.classList.toggle('open',open);toggle.setAttribute('aria-expanded',String(open));if(open)search.focus()}});
  root.querySelectorAll('input[type=checkbox]').forEach(input=>input.addEventListener('change',()=>{{if(input.checked)state[key].add(input.value);else state[key].delete(input.value);scheduleRender()}}));
  search.addEventListener('input',()=>{{const term=search.value.trim().toLocaleLowerCase();root.querySelectorAll('.option').forEach(option=>option.hidden=!option.dataset.search.includes(term))}});
  clear.addEventListener('click',()=>{{state[key].clear();scheduleRender()}});
}}
function refreshPicker(id,label,key,total){{const root=byId(id),selected=state[key],all=!selected.size||selected.size===total;root.querySelector('[data-label]').textContent=selectedText(label,selected,total);root.querySelector('[data-status]').textContent=all?'All selected':`${{selected.size}} selected`;root.querySelectorAll('input[type=checkbox]').forEach(input=>input.checked=selected.has(input.value))}}
function matches(row,includePlatform,channelActive,regionActive,stateActive,platformActive){{return row[1]===state.source&&(!state.from||row[0]>=state.from)&&(!state.to||row[0]<=state.to)&&(!channelActive||state.channels.has(row[4]))&&(!regionActive||state.regions.has(row[2]))&&(!stateActive||state.states.has(row[3]))&&(!includePlatform||!platformActive||state.platforms.has(row[7]))}}
function niceStep(maxValue){{if(maxValue<=0)return 1;const rough=maxValue/5,power=10**Math.floor(Math.log10(rough)),normalized=rough/power;return (normalized<=1?1:normalized<=2?2:normalized<=2.5?2.5:normalized<=5?5:10)*power}}
function renderChart(dates,totals,targetId){{const chart=byId(targetId),svg=chart,yAxis=byId(`${{targetId}}YAxis`),compact=dates.length<=7,height=compact?220:280,left=0,right=18,top=14,viewportWidth=Math.max(320,chart.parentElement?.clientWidth||900),minimumSlot=54,width=Math.max(viewportWidth,Math.max(1,dates.length)*minimumSlot),slot=width/Math.max(1,dates.length),barWidth=Math.min(36,Math.max(14,slot*.62)),innerHeight=height-top-58;chart.closest('.chart-section').classList.toggle('compact',compact);chart.setAttribute('viewBox',`0 0 ${{width}} ${{height}}`);chart.style.width=`${{width}}px`;chart.style.minWidth=`${{width}}px`;yAxis.style.height=`${{height}}px`;const values=dates.map(date=>totals.get(date)||0),maxValue=Math.max(0,...values),step=niceStep(maxValue),axisMax=Math.max(step,Math.ceil(maxValue/step)*step+step),ticks=5;const grid=[];const axisLabels=[];for(let i=0;i<=ticks;i++){{const value=axisMax*i/ticks,y=top+innerHeight-(value/axisMax)*innerHeight;grid.push(`<line class="chart-grid" x1="${{left}}" x2="${{width-right}}" y1="${{y}}" y2="${{y}}"></line>`);axisLabels.push(`<span class="chart-y-axis-label" style="top:${{y}}px">${{escapeHtml(formatAxis(value))}}</span>`)}}yAxis.innerHTML=axisLabels.join('');if(!dates.length){{svg.innerHTML='<text class="chart-empty" x="12" y="45">No data for the selected filters</text>';return}}const bars=dates.map((date,index)=>{{const value=values[index],barHeight=value/axisMax*innerHeight,x=index*slot+(slot-barWidth)/2,y=top+innerHeight-barHeight,label=new Date(`${{date}}T00:00:00`).toLocaleDateString('en-IN',{{day:'2-digit',month:'short'}}),labelX=x+barWidth/2,valueLabel=`<text class="chart-value-label" x="${{labelX}}" y="${{Math.max(top+12,y-10)}}">${{escapeHtml(formatAxis(value))}}</text>`;return `<rect class="chart-bar" fill="url(#barGradient-${{targetId}})" x="${{x}}" y="${{y}}" width="${{barWidth}}" height="${{Math.max(0,barHeight)}}" rx="4"></rect>${{valueLabel}}<text class="chart-x-label" x="${{labelX}}" y="${{height-26}}">${{escapeHtml(label)}}</text>`}}).join('');svg.innerHTML=`<defs><linearGradient id="barGradient-${{targetId}}" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#3caea3"></stop><stop offset="100%" stop-color="#176b87"></stop></linearGradient></defs>${{grid.join('')}}<line class="chart-axis" x1="${{left}}" x2="${{width-right}}" y1="${{top+innerHeight}}" y2="${{top+innerHeight}}"></line>${{bars}}`}}
function renderIdentityChart(dates,targetId){{const section=byId(targetId==='identityChart'?'identitySection':'streamIdentitySection'),chart=byId(targetId),svg=chart,yAxis=byId(`${{targetId}}YAxis`),source=String(state.source||'').trim().toLowerCase(),compact=dates.length<=7,height=compact?220:280,left=0,right=18,top=14,slot=60,barWidth=20,width=right+Math.max(1,dates.length)*slot,innerHeight=height-top-58;section.hidden=source!=='stream';if(source!=='stream'){{svg.innerHTML='';yAxis.innerHTML='';return}}chart.closest('.chart-section').classList.toggle('compact',compact);chart.setAttribute('viewBox',`0 0 ${{width}} ${{height}}`);chart.style.width=`${{width}}px`;chart.style.minWidth=`${{width}}px`;yAxis.style.height=`${{height}}px`;const identity=new Map(identityRows.filter(row=>String(row[1]||'').trim().toLowerCase()===source&&(!state.from||row[0]>=state.from)&&(!state.to||row[0]<=state.to)).map(row=>[row[0],[Number(row[2]||0),Number(row[3]||0)]]));const values=dates.map(date=>identity.get(date)||[0,0]),maxValue=Math.max(0,...values.flat()),step=niceStep(maxValue),axisMax=Math.max(step,Math.ceil(maxValue/step)*step+step),ticks=5,grid=[],axisLabels=[];for(let i=0;i<=ticks;i++){{const value=axisMax*i/ticks,y=top+innerHeight-(value/axisMax)*innerHeight;grid.push(`<line class="chart-grid" x1="${{left}}" x2="${{width-right}}" y1="${{y}}" y2="${{y}}"></line>`);axisLabels.push(`<span class="chart-y-axis-label" style="top:${{y}}px">${{escapeHtml(formatAxis(value))}}</span>`)}}yAxis.innerHTML=axisLabels.join('');if(!dates.length){{svg.innerHTML='';return}}const bars=dates.map((date,index)=>{{const [device,session]=values[index],label=new Date(`${{date}}T00:00:00`).toLocaleDateString('en-IN',{{day:'2-digit',month:'short'}}),base=index*slot,deviceHeight=device/axisMax*innerHeight,sessionHeight=session/axisMax*innerHeight,deviceX=base+8,sessionX=base+32,deviceY=top+innerHeight-deviceHeight,sessionY=top+innerHeight-sessionHeight;return `<rect class="chart-bar" fill="#2f9e8f" x="${{deviceX}}" y="${{deviceY}}" width="${{barWidth}}" height="${{Math.max(0,deviceHeight)}}" rx="3"></rect><rect class="chart-bar" fill="#176b87" x="${{sessionX}}" y="${{sessionY}}" width="${{barWidth}}" height="${{Math.max(0,sessionHeight)}}" rx="3"></rect><text class="chart-value-label" x="${{deviceX+barWidth/2}}" y="${{Math.max(top+12,deviceY-5)}}">${{escapeHtml(formatAxis(device))}}</text><text class="chart-value-label" x="${{sessionX+barWidth/2}}" y="${{Math.max(top+12,sessionY-5)}}">${{escapeHtml(formatAxis(session))}}</text><text class="chart-x-label" x="${{base+30}}" y="${{height-26}}">${{escapeHtml(label)}}</text>`}}).join('');svg.innerHTML=`${{grid.join('')}}<line class="chart-axis" x1="${{left}}" x2="${{width-right}}" y1="${{top+innerHeight}}" y2="${{top+innerHeight}}"></line>${{bars}}`}}
function renderMetricDetail(bodyId,dates,values,formatter){{const body=byId(bodyId);body.innerHTML=dates.map(date=>{{const label=new Date(`${{date}}T00:00:00`).toLocaleDateString('en-IN',{{day:'2-digit',month:'short'}});return `<tr><td>${{escapeHtml(label)}}</td><td>${{escapeHtml(formatter(values.get(date)||0))}}</td></tr>`}}).join('')}}
function renderIdentityDetail(dates){{const body=byId('streamIdentityDetailBody'),identity=new Map(identityRows.filter(row=>row[1]==='stream').map(row=>[row[0],[Number(row[2]||0),Number(row[3]||0)]]));body.innerHTML=dates.map(date=>{{const [devices,sessions]=identity.get(date)||[0,0],label=new Date(`${{date}}T00:00:00`).toLocaleDateString('en-IN',{{day:'2-digit',month:'short'}});return `<tr><td>${{escapeHtml(label)}}</td><td>${{escapeHtml(formatNumber.format(devices))}}</td><td>${{escapeHtml(formatNumber.format(sessions))}}</td></tr>`}}).join('')}}
function renderDailyDetail(dates,totals,viewerTotals){{const body=byId('dailyDetailBody'),scroll=byId('dailyDetailScroll'),previousTop=scroll?scroll.scrollTop:0;body.innerHTML=dates.map(date=>{{const label=new Date(`${{date}}T00:00:00`).toLocaleDateString('en-IN',{{day:'2-digit',month:'short'}});return `<tr><td>${{escapeHtml(label)}}</td><td>${{escapeHtml(formatHours.format(totals.get(date)||0))}}</td><td>${{escapeHtml(formatNumber.format(Math.round(viewerTotals.get(date)||0)))}}</td></tr>`}}).join('');if(scroll)requestAnimationFrame(()=>{{scroll.scrollTop=Math.min(previousTop,Math.max(0,scroll.scrollHeight-scroll.clientHeight))}})}}
const uaLevels=[
  {{key:'device',index:5,title:'Device Types',crumb:'Device'}},
  {{key:'model',index:6,title:'Device Models',crumb:'Model'}},
  {{key:'os',index:7,title:'Operating Systems',crumb:'OS'}},
  {{key:'os_detail',index:8,title:'OS Versions / Detailed OS',crumb:'Version'}},
];
let uaBookLevel=0,uaAvailableDepth=4,uaCurrentRows=[],uaFilterKey='';
const uaPath=[null,null,null,null];
function clearUaPathFrom(level){{for(let index=level;index<uaPath.length;index++)uaPath[index]=null}}
function maxUaLevel(){{const firstMissing=uaPath.findIndex((value,index)=>index<uaAvailableDepth&&value===null);return Math.min(uaAvailableDepth-1,firstMissing<0?uaAvailableDepth-1:firstMissing)}}
function renderUaBreadcrumb(){{
  const parts=['All devices',...uaPath.slice(0,uaAvailableDepth).filter(Boolean)];
  byId('uaBreadcrumb').innerHTML=parts.map((part,index)=>index===parts.length-1?`<strong>${{escapeHtml(part)}}</strong>`:escapeHtml(part)).join(' &gt; ');
}}
function renderUaHierarchy(){{
  const level=uaLevels[uaBookLevel],totals=new Map();
  uaCurrentRows.forEach(row=>{{
    for(let index=0;index<uaBookLevel;index++)if(uaPath[index]!==null&&row[uaLevels[index].index]!==uaPath[index])return;
    const label=String(row[level.index]||'Unknown / NA');totals.set(label,(totals.get(label)||0)+Number(row[9]||0));
  }});
  const ranked=[...totals].map(([label,hours])=>({{label,hours}})).sort((a,b)=>b.hours-a.hours||a.label.localeCompare(b.label));
  const target=byId('uaHierarchyList'),count=byId('uaHierarchyCount'),total=ranked.reduce((sum,item)=>sum+item.hours,0),max=ranked.length?ranked[0].hours:0;
  byId('uaHierarchyTitle').textContent=level.title;count.textContent=`${{formatNumber.format(ranked.length)}} values`;
  target.innerHTML=ranked.length?ranked.map((item,index)=>{{
    const share=total?item.hours*100/total:0,width=max?Math.max(1,item.hours*100/max):0,selected=uaPath[uaBookLevel]===item.label;
    return `<button type="button" class="ua-row${{selected?' selected':''}}" data-ua-value="${{escapeHtml(item.label)}}"><span class="ua-rank">${{index+1}}</span><span class="ua-main"><span class="ua-name" title="${{escapeHtml(item.label)}}">${{escapeHtml(item.label)}}</span><span class="ua-track"><span class="ua-fill" style="width:${{width.toFixed(2)}}%"></span></span></span><span class="ua-value">${{escapeHtml(formatHours.format(item.hours))}}<span class="ua-share">${{share.toFixed(1)}}%</span></span><span class="ua-drill">${{uaBookLevel<uaAvailableDepth-1?'&gt;':''}}</span></button>`;
  }}).join(''):'<div class="ua-empty">No matching data at this level</div>';
  target.querySelectorAll('[data-ua-value]').forEach(button=>button.addEventListener('click',()=>{{
    uaPath[uaBookLevel]=button.dataset.uaValue;clearUaPathFrom(uaBookLevel+1);
    if(uaBookLevel<uaAvailableDepth-1)uaBookLevel+=1;
    setUaBookLevel(uaBookLevel);
  }}));
  renderUaBreadcrumb();
}}
function setUaBookLevel(level){{
  const requested=Math.max(0,Math.min(uaAvailableDepth-1,Number(level)||0));uaBookLevel=Math.min(requested,maxUaLevel());
  const navigable=maxUaLevel();
  document.querySelectorAll('[data-ua-level]').forEach(button=>{{const index=Number(button.dataset.uaLevel),active=index===uaBookLevel;button.classList.toggle('active',active);button.setAttribute('aria-current',active?'step':'false');button.disabled=index>=uaAvailableDepth||index>navigable}});
  byId('deviceBookPosition').textContent=`${{uaBookLevel+1}} of ${{uaAvailableDepth}}`;
  byId('deviceBookPrevious').disabled=uaBookLevel===0;byId('deviceBookNext').disabled=uaBookLevel>=uaAvailableDepth-1||uaPath[uaBookLevel]===null;
  renderUaHierarchy();
}}
function renderDeviceAndOs(channelActive,regionActive,stateActive,platformActive){{
  const section=byId('deviceOsSection'),status=byId('deviceOsStatus');byId('evidenceGrid').hidden=false;section.hidden=false;
  const nextFilterKey=JSON.stringify([state.source,state.from,state.to,[...state.channels].sort(),[...state.platforms].sort(),[...state.regions].sort(),[...state.states].sort()]);
  if(nextFilterKey!==uaFilterKey){{uaFilterKey=nextFilterKey;clearUaPathFrom(0);uaBookLevel=0}}
  if(regionActive||stateActive){{
    uaCurrentRows=[];uaAvailableDepth=1;status.textContent='Device hierarchy is not available at Region or State grain';
    byId('uaHierarchyList').innerHTML='<div class="ua-empty">No joint Device / OS mart exists for this geographic selection</div>';byId('uaHierarchyCount').textContent='';setUaBookLevel(0);return;
  }}
  if(state.source==='stream'&&channelActive){{
    uaAvailableDepth=1;status.textContent='STREAM channel data supports Device Type only';
    uaCurrentRows=uaRows.filter(row=>row[1]==='stream'&&row[3]==='device'&&row[5]==='channel'&&state.channels.has(row[2])&&(!state.from||row[0]>=state.from)&&(!state.to||row[0]<=state.to)).map(row=>[row[0],row[1],'stream_channel',row[2],'',row[4],'Unknown / NA','Unknown / NA','Unknown / NA',Number(row[6]||0)]);
  }}else{{
    const useFastDetail=state.source==='fast'&&(channelActive||platformActive);uaAvailableDepth=4;status.textContent='Click a row to drill into its associated children';
    uaCurrentRows=uaHierarchyRows.filter(row=>row[1]===state.source&&(!state.from||row[0]>=state.from)&&(!state.to||row[0]<=state.to)&&(useFastDetail?row[2]==='fast_detail'&&(!channelActive||state.channels.has(row[3]))&&(!platformActive||state.platforms.has(row[4])):row[2]==='source'));
  }}
  setUaBookLevel(uaBookLevel);
}}
let networkMode='all';
function networkIsDecoded(row){{const name=String(row.name||'').trim().toLowerCase(),status=String(row.status||'').trim().toLowerCase();return Boolean(name&&name!=='unknown'&&name!=='unknown / na'&&status!=='unknown'&&status!=='unmapped')}}
function renderNetworks(channelActive,regionActive,stateActive,platformActive){{
  const status=byId('networkStatus'),list=byId('networkList'),count=byId('networkCount'),coverage=byId('networkCoverage'),counts=byId('networkCounts'),watch=byId('networkWatchHours'),activityHelp=byId('networkActivityHelp');
  const unavailable=channelActive||regionActive||stateActive||(state.source==='fast'&&platformActive);
  if(unavailable){{
    status.textContent='Available for Date and Source filters';count.textContent='';coverage.textContent='Provider mapping: Not available';counts.textContent='Source-level data only';watch.textContent='Selected Total: Not available';activityHelp.textContent='Reset Channel, Platform, Region, and State to view providers';
    list.innerHTML='<div class="ua-empty">Select All Channels, Platforms, Regions, and States to view source-level network evidence</div>';return;
  }}
  const sourceRows=asnRows.filter(row=>row[1]===state.source&&(!state.from||row[0]>=state.from)&&(!state.to||row[0]<=state.to)),activeDates=new Set(sourceRows.map(row=>row[0])),singleDay=activeDates.size===1,activityLabel=singleDay?'active IPs':'IP-days',averageLabel=singleDay?'avg min / active IP':'avg min / IP-day';
  status.textContent=singleDay?'Internet provider traffic for the selected day':`Internet provider traffic across ${{formatNumber.format(activeDates.size)}} selected days`;
  const totals=new Map();
  sourceRows.forEach(row=>{{
    const key=String(row[2]||'0'),item=totals.get(key)||{{asn:key,name:String(row[3]||'Unknown / NA'),country:String(row[4]||'Unknown / NA'),domain:String(row[5]||''),type:String(row[6]||'Unknown / NA'),status:String(row[7]||'unmapped'),rawRows:0,ips:0}};
    item.rawRows+=Number(row[8]||0);item.ips+=Number(row[9]||0);totals.set(key,item);
  }});
  const all=[...totals.values()],decoded=all.filter(networkIsDecoded),allRows=all.reduce((sum,row)=>sum+row.rawRows,0),decodedRows=decoded.reduce((sum,row)=>sum+row.rawRows,0),needle=byId('networkSearch').value.trim().toLowerCase();
  const ranked=all.filter(row=>{{const isDecoded=networkIsDecoded(row),modeOk=networkMode==='all'||(networkMode==='decoded'&&isDecoded)||(networkMode==='unresolved'&&!isDecoded),haystack=`AS${{row.asn}} ${{row.name}} ${{row.country}} ${{row.domain}} ${{row.type}}`.toLowerCase();return modeOk&&(!needle||haystack.includes(needle))}}).sort((a,b)=>b.rawRows-a.rawRows||a.name.localeCompare(b.name));
  const max=ranked.length?ranked[0].rawRows:0,totalHours=allRows/600,mappedPercent=allRows?decodedRows*100/allRows:0;
  coverage.innerHTML=`<strong>${{mappedPercent.toFixed(1)}}%</strong> of watch traffic mapped to named providers`;counts.textContent=`${{formatNumber.format(all.length)}} networks: ${{formatNumber.format(decoded.length)}} identified, ${{formatNumber.format(all.length-decoded.length)}} unresolved`;count.textContent=`${{formatNumber.format(ranked.length)}} shown | ranked by watch hours`;watch.textContent=`Selected Total: ${{formatHours.format(totalHours)}} watch hrs`;activityHelp.textContent=singleDay?'Active IPs are distinct network addresses for this day, not people':'IP-days add each day\'s distinct network addresses; the same IP can count again on another day';
  list.innerHTML=ranked.length?ranked.map((row,index)=>{{const hours=row.rawRows/600,width=max?Math.max(1,row.rawRows*100/max):0,share=allRows?row.rawRows*100/allRows:0,averageMinutes=row.ips?hours*60/row.ips:0,name=networkIsDecoded(row)?row.name:'Unknown / NA',metadata=[row.country,row.type,row.domain].filter(value=>value&&value!=='Unknown / NA').join(' | ')||'Provider mapping unavailable';return `<div class="network-row"><span class="ua-rank">${{index+1}}</span><div class="network-main"><div class="network-name" title="AS${{escapeHtml(row.asn)}} - ${{escapeHtml(name)}}">AS${{escapeHtml(row.asn)}} - ${{escapeHtml(name)}}</div><div class="network-meta" title="${{escapeHtml(metadata)}}">${{escapeHtml(metadata)}}</div><div class="ua-track" title="${{share.toFixed(1)}}% of selected watch traffic"><div class="ua-fill" style="width:${{width.toFixed(2)}}%"></div></div></div><div class="network-value"><strong>${{escapeHtml(formatHours.format(hours))}} <small>watch hrs</small></strong><span class="network-share">${{share.toFixed(1)}}% of selected traffic</span><span>${{escapeHtml(formatNumber.format(row.ips))}} ${{activityLabel}} | ${{escapeHtml(formatNumber.format(Math.round(averageMinutes)))}} ${{averageLabel}}</span></div></div>`}}).join(''):'<div class="ua-empty">No matching provider data</div>';
}}
function renderNetworksFromState(){{const channelTotal=channelsForSource(state.source).length,channelActive=state.channels.size>0&&state.channels.size<channelTotal,regionActive=state.regions.size>0&&state.regions.size<allRegions.length,stateActive=state.states.size>0&&state.states.size<allStates.length,platformActive=state.source==='fast'&&state.platforms.size>0&&state.platforms.size<allPlatforms.length;renderNetworks(channelActive,regionActive,stateActive,platformActive)}}
function initialiseDeviceBook(){{
  document.querySelectorAll('[data-ua-level]').forEach(button=>button.addEventListener('click',()=>setUaBookLevel(button.dataset.uaLevel)));
  byId('deviceBookPrevious').addEventListener('click',()=>setUaBookLevel(uaBookLevel-1));
  byId('deviceBookNext').addEventListener('click',()=>setUaBookLevel(uaBookLevel+1));
  byId('deviceBookReset').addEventListener('click',()=>{{clearUaPathFrom(0);setUaBookLevel(0)}});
}}
function initialiseNetworks(){{
  byId('networkSearch').addEventListener('input',renderNetworksFromState);
  byId('networkModes').querySelectorAll('[data-network-mode]').forEach(button=>button.addEventListener('click',()=>{{networkMode=button.dataset.networkMode;byId('networkModes').querySelectorAll('[data-network-mode]').forEach(item=>item.classList.toggle('active',item===button));renderNetworksFromState()}}));
}}
function render(){{const channelTotal=channelsForSource(state.source).length,regionTotal=allRegions.length,stateTotal=allStates.length,platformTotal=allPlatforms.length;const channelActive=state.channels.size>0&&state.channels.size<channelTotal,regionActive=state.regions.size>0&&state.regions.size<regionTotal,stateActive=state.states.size>0&&state.states.size<stateTotal,platformActive=state.platforms.size>0&&state.platforms.size<platformTotal;const usePlatform=state.source==='fast'&&platformActive;const activeRows=usePlatform?platformRows:rows;const scoped=activeRows.filter(row=>matches(row,usePlatform,channelActive,regionActive,stateActive,platformActive));const hours=scoped.reduce((total,row)=>total+Number(row[5]||0),0),viewers=scoped.reduce((total,row)=>total+Number(row[6]||0),0);const visibleDates=unique(0).filter(date=>(!state.from||date>=state.from)&&(!state.to||date<=state.to)&&rows.some(row=>row[1]===state.source&&row[0]===date));const totals=new Map(visibleDates.map(date=>[date,0])),viewerTotals=new Map(visibleDates.map(date=>[date,0]));scoped.forEach(row=>{{totals.set(row[0],(totals.get(row[0])||0)+Number(row[5]||0));viewerTotals.set(row[0],(viewerTotals.get(row[0])||0)+Number(row[6]||0))}});const hoursText=formatHours.format(hours),viewersText=formatNumber.format(Math.round(viewers)),isStream=String(state.source||'').toLowerCase()==='stream';byId('watchHoursHeadingValue').textContent=`Total Watch Hours: ${{hoursText}}`;byId('viewersHeadingValue').textContent=`Total Viewers: ${{viewersText}}`;byId('defaultLayout').hidden=true;byId('streamMatrix').hidden=false;byId('streamIdentityRow').hidden=!isStream;renderChart(visibleDates,totals,'streamWatchChart');renderChart(visibleDates,viewerTotals,'streamViewerChart');renderMetricDetail('streamWatchDetailBody',visibleDates,totals,value=>formatHours.format(value));renderMetricDetail('streamViewerDetailBody',visibleDates,viewerTotals,value=>formatNumber.format(Math.round(value)));if(isStream){{renderIdentityChart(visibleDates,'streamIdentityChart');renderIdentityDetail(visibleDates)}}byId('streamWatchTotal').textContent=`Total Watch Hours: ${{hoursText}}`;byId('streamViewerTotal').textContent=`Total Viewers: ${{viewersText}}`;byId('summaryRail').classList.toggle('bounded',visibleDates.length>7);byId('platformField').hidden=state.source!=='fast';refreshPicker('channelPicker','Channels','channels',channelTotal);refreshPicker('regionPicker','Regions','regions',regionTotal);refreshPicker('statePicker','States','states',stateTotal);refreshPicker('platformPicker','Platforms','platforms',platformTotal);renderDeviceAndOs(channelActive,regionActive,stateActive,platformActive);renderNetworks(channelActive,regionActive,stateActive,platformActive)}}
function escapeHtml(value){{return String(value).replace(/[&<>'"]/g,char=>({{'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}}[char]))}}
function scheduleRender(){{const token=++renderToken,overlay=byId('loadingOverlay');overlay.classList.add('active');overlay.setAttribute('aria-hidden','false');requestAnimationFrame(()=>{{render();window.setTimeout(()=>{{if(token!==renderToken)return;overlay.classList.remove('active');overlay.setAttribute('aria-hidden','true')}},90)}})}}
function initialise(){{const dates=unique(0);const minDate=dates[0]||'',maxDate=dates.at(-1)||'';state.from=minDate;state.to=maxDate;
  const from=byId('dateFrom'),to=byId('dateTo'),preset=byId('datePreset');
  const setRange=(value)=>{{const last=dates.length-1;let start=dates[0]||'',end=dates[last]||'';if(value==='yesterday'&&last>0)start=end=dates[last-1];else if(value!=='all'&&value!=='custom'){{const count=Number(value);start=dates[Math.max(0,dates.length-count)]||start}}state.from=start;state.to=end;from.value=start;to.value=end;syncDateBounds();scheduleRender()}};
  const syncDateBounds=()=>{{from.min=minDate;from.max=state.to||maxDate;to.min=state.from||minDate;to.max=maxDate}};
  preset.value='7';setRange('7');
  preset.addEventListener('change',()=>setRange(preset.value));
  from.addEventListener('change',()=>{{preset.value='custom';state.from=from.value;if(state.from&&state.to&&state.from>state.to){{state.to=state.from;to.value=state.to}}syncDateBounds();scheduleRender()}});
  to.addEventListener('change',()=>{{preset.value='custom';state.to=to.value;if(state.from&&state.to&&state.to<state.from){{state.from=state.to;from.value=state.from}}syncDateBounds();scheduleRender()}});
  ['dailyDetailScroll','streamWatchDetailScroll','streamViewerDetailScroll','streamIdentityDetailScroll'].forEach(id=>{{const detailScroll=byId(id);detailScroll.addEventListener('wheel',event=>{{if(detailScroll.scrollHeight<=detailScroll.clientHeight)return;event.preventDefault();const page=27*15;detailScroll.scrollTop+=event.deltaY>0?page:-page}},{{passive:false}})}});
  buildSource();buildChannelPicker();buildPicker('regionPicker','Regions',allRegions,'regions');buildPicker('statePicker','States',allStates,'states');buildPicker('platformPicker','Platforms',allPlatforms,'platforms');
  document.addEventListener('click',event=>{{if(!event.target.closest('.multi-picker'))document.querySelectorAll('.multi-menu.open').forEach(menu=>menu.classList.remove('open'))}});
  render()}}
const attachBarTitles=(chartId,bodyId,columns)=>{{const svg=byId(chartId),body=byId(bodyId);if(!svg||!body)return;const values=[...body.querySelectorAll('tr')].map(row=>[...row.cells].map(cell=>cell.textContent.trim()));[...svg.querySelectorAll('rect.chart-bar')].forEach((bar,index)=>{{const row=values[Math.floor(index/columns)]||[],value=row[(index%columns)+1]||'0';bar.setAttribute('title',value);bar.setAttribute('aria-label',value)}})}};
const refreshBarTitles=()=>{{attachBarTitles('streamWatchChart','streamWatchDetailBody',1);attachBarTitles('streamViewerChart','streamViewerDetailBody',1);attachBarTitles('streamIdentityChart','streamIdentityDetailBody',2)}};
const barTitleObserver=new MutationObserver(refreshBarTitles);barTitleObserver.observe(byId('streamMatrix'),{{childList:true,subtree:true}});
const refreshGraphHeaders=()=>{{const watchSection=byId('streamWatchChart')?.closest('.chart-section'),viewerSection=byId('streamViewerChart')?.closest('.chart-section');if(watchSection){{watchSection.querySelector('.chart-title span').textContent='Watch Hours';const watchRows=[...byId('streamWatchDetailBody').querySelectorAll('tr')],viewerRows=[...byId('streamViewerDetailBody').querySelectorAll('tr')],hours=watchRows.reduce((sum,row)=>sum+(Number(String(row.cells[1]?.textContent||'0').replace(/,/g,''))||0),0),viewers=viewerRows.reduce((sum,row)=>sum+(Number(String(row.cells[1]?.textContent||'0').replace(/,/g,''))||0),0),seconds=viewers?hours*3600/viewers:0,average=seconds>=60?`${{(seconds/60).toFixed(1)}} min`:`${{Math.round(seconds)}} sec`;byId('streamWatchTotal').textContent=`Total Watch Hours: ${{formatNumber.format(hours)}} | Avg. Watch Time / User: ${{average}}`}}if(viewerSection)viewerSection.querySelector('.chart-title span').textContent='Viewers'}};
initialise();initialiseDeviceBook();initialiseNetworks();refreshBarTitles();refreshGraphHeaders();
const renderConcurrencyLegacy=()=>{{const chart=byId('concurrencyChart'),axis=byId('concurrencyChartYAxis'),body=byId('concurrencyDetailBody'),source=String(state.source||'').toLowerCase(),step=Number(byId('concurrencyResolution')?.value||1),channelTotal=channelsForSource(source).length,platformTotal=allPlatforms.length,channelActive=state.channels.size>0&&state.channels.size<channelTotal,platformActive=source==='fast'&&state.platforms.size>0&&state.platforms.size<platformTotal,selected=concurrencyRows.filter(row=>row[1]===source&&(!state.from||row[0]>=state.from)&&(!state.to||row[0]<=state.to)&&(!channelActive||state.channels.has(row[4]))&&(!platformActive||state.platforms.has(row[5]))),dates=unique(0).filter(date=>(!state.from||date>=state.from)&&(!state.to||date<=state.to)&&rows.some(row=>row[1]===source&&row[0]===date)),pad=value=>String(value).padStart(2,'0'),toMinute=value=>{{const match=String(value).match(/^(\d{{4}}-\d{{2}}-\d{{2}}) (\d{{2}}):(\d{{2}})/);if(!match)return null;const minute=Math.floor(Number(match[3])/step)*step;return {{key:`${{match[1]}} ${{match[2]}}:${{pad(minute)}}`,time:Date.parse(`${{match[1]}}T${{match[2]}}:${{pad(minute)}}:00+05:30`),date:match[1]}}}};const buckets=new Map;selected.forEach(row=>{{const bucket=toMinute(row[2]);if(!bucket)return;const item=buckets.get(bucket.key)||{{time:bucket.time,date:bucket.date,sum:0,count:0}};item.sum+=Number(row[3]||0);item.count+=1;buckets.set(bucket.key,item)}});const points=[...buckets.values()].sort((a,b)=>a.time-b.time).map(item=>({{...item,value:item.count?Math.round(item.sum/item.count):0}}));const detail=new Map(dates.map(date=>[date,[]]));points.forEach(point=>{{if(detail.has(point.date))detail.get(point.date).push(point.value)}});body.innerHTML=dates.map(date=>{{const values=detail.get(date)||[],avg=values.length?Math.round(values.reduce((sum,value)=>sum+value,0)/values.length):null,peak=values.length?Math.max(...values):null,label=new Date(`${{date}}T00:00:00`).toLocaleDateString('en-IN',{{day:'2-digit',month:'short'}});return `<tr><td>${{escapeHtml(label)}}</td><td>${{avg===null?'—':escapeHtml(formatNumber.format(avg))}}</td><td>${{peak===null?'—':escapeHtml(formatNumber.format(peak))}}</td></tr>`}}).join('');const start=Date.parse(`${{state.from||dates[0]||'1970-01-01'}}T00:00:00+05:30`),end=Date.parse(`${{state.to||dates.at(-1)||state.from||'1970-01-01'}}T23:59:00+05:30`),minuteWidth=3,width=Math.max(900,Math.ceil((end-start)/60000)*minuteWidth+30),height=240,top=14,bottom=42,left=0,right=18,innerHeight=height-top-bottom,maxValue=Math.max(0,...points.map(point=>point.value)),stepSize=niceStep(maxValue),axisMax=Math.max(stepSize,Math.ceil(maxValue/stepSize)*stepSize+stepSize),axisLabels=[],grid=[];for(let i=0;i<=5;i++){{const value=axisMax*i/5,y=top+innerHeight-(value/axisMax)*innerHeight;grid.push(`<line class="chart-grid" x1="${{left}}" x2="${{width-right}}" y1="${{y}}" y2="${{y}}"></line>`);axisLabels.push(`<span class="chart-y-axis-label" style="top:${{y}}px">${{escapeHtml(formatAxis(value))}}</span>`)}}axis.innerHTML=axisLabels.join('');const xFor=time=>left+((time-start)/60000)*minuteWidth,yFor=value=>top+innerHeight-(value/axisMax)*innerHeight,paths=[],dots=[],dateLabels=dates.map(date=>{{const time=Date.parse(`${{date}}T00:00:00+05:30`),x=xFor(time),label=new Date(`${{date}}T00:00:00`).toLocaleDateString('en-IN',{{day:'2-digit',month:'short'}});return `<text class="chart-x-label" x="${{x}}" y="${{height-10}}">${{escapeHtml(label)}}</text>`}}).join('');let segment=[];const flush=()=>{{if(segment.length>1)paths.push(`<path class="concurrency-line" d="M ${{segment.map(point=>`${{xFor(point.time)}} ${{yFor(point.value)}}`).join(' L ')}}"></path>`);segment=[]}};points.forEach((point,index)=>{{const previous=points[index-1];if(previous&&point.time-previous.time>step*60000*1.5)flush();segment.push(point);dots.push(`<circle class="concurrency-dot" cx="${{xFor(point.time)}}" cy="${{yFor(point.value)}}" r="2"><title>${{escapeHtml(formatNumber.format(point.value))}}</title></circle>`)}});flush();chart.setAttribute('viewBox',`0 0 ${{width}} ${{height}}`);chart.style.width=`${{width}}px`;chart.style.minWidth=`${{width}}px`;axis.style.height=`${{height}}px`;chart.innerHTML=`${{grid.join('')}}<line class="chart-axis" x1="${{left}}" x2="${{width-right}}" y1="${{top+innerHeight}}" y2="${{top+innerHeight}}"></line>${{paths.join('')}}${{dots.join('')}}${{dateLabels}}`;byId('concurrencyTotal').textContent=`Peak Users: ${{formatNumber.format(maxValue)}} | ${{step===1?'Minute':'5-Minute'}}`}};
function renderConcurrencySlidingLegacy(){{
  const chart=byId('concurrencyChart'),axis=byId('concurrencyChartYAxis'),body=byId('concurrencyDetailBody');
  const note=byId('concurrencyNote');
  const source=String(state.source||'').toLowerCase(),step=Number(byId('concurrencyResolution')?.value||1);
  const channelTotal=channelsForSource(source).length,platformTotal=allPlatforms.length;
  const channelActive=state.channels.size>0&&state.channels.size<channelTotal;
  const platformActive=source==='fast'&&state.platforms.size>0&&state.platforms.size<platformTotal;
  const selected=concurrencyRows.filter(row=>row[1]===source&&(!state.from||row[0]>=state.from)&&(!state.to||row[0]<=state.to)&&(!channelActive||state.channels.has(row[4]))&&(!platformActive||state.platforms.has(row[5])));
  const availableDates=unique(0).filter(date=>(!state.from||date>=state.from)&&(!state.to||date<=state.to)&&rows.some(row=>row[1]===source&&row[0]===date));
  const rangeStart=state.from||availableDates[0]||'',rangeEnd=state.to||availableDates.at(-1)||rangeStart,dates=[];
  if(rangeStart&&rangeEnd){{for(let cursor=new Date(`${{rangeStart}}T00:00:00Z`),last=new Date(`${{rangeEnd}}T00:00:00Z`);cursor<=last;cursor.setUTCDate(cursor.getUTCDate()+1))dates.push(cursor.toISOString().slice(0,10))}}
  const pad=value=>String(value).padStart(2,'0');
  const parseMinute=value=>{{
    const match=String(value).match(/^([0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}) ([0-9]{{2}}):([0-9]{{2}})/);
    if(!match)return null;
    const minute=Math.floor(Number(match[3])/step)*step;
    return {{date:match[1],time:Date.parse(`${{match[1]}}T${{match[2]}}:${{pad(minute)}}:00+05:30`),minuteOfDay:Number(match[2])*60+minute,key:`${{match[1]}} ${{match[2]}}:${{pad(minute)}}`}};
  }};
  const minuteTotals=new Map();
  selected.forEach(row=>{{
    const minute=parseMinute(row[2]);
    if(!minute)return;
    const key=`${{minute.date}} ${{String(row[2]).slice(11,16)}}`;
    minuteTotals.set(key,(minuteTotals.get(key)||0)+Number(row[3]||0));
  }});
  const buckets=new Map();
  minuteTotals.forEach((value,key)=>{{
    const minute=parseMinute(key);
    if(!minute)return;
    const bucket=buckets.get(minute.key)||{{date:minute.date,time:minute.time,minuteOfDay:minute.minuteOfDay,value:0}};
    bucket.value+=value;
    buckets.set(minute.key,bucket);
  }});
  const points=[...buckets.values()].sort((a,b)=>a.time-b.time);
  const detail=new Map(dates.map(date=>[date,[]]));
  points.forEach(point=>{{if(detail.has(point.date))detail.get(point.date).push(point.value)}});
  body.innerHTML=dates.map(date=>{{
    const values=detail.get(date)||[],minuteSum=values.length?values.reduce((sum,value)=>sum+value,0):null,peak=values.length?Math.max(...values):null;
    const label=new Date(`${{date}}T00:00:00`).toLocaleDateString('en-IN',{{day:'2-digit',month:'short'}});
    return `<tr><td>${{escapeHtml(label)}}</td><td>${{minuteSum===null?'—':escapeHtml(formatNumber.format(Math.round(minuteSum)))}}</td><td>${{peak===null?'—':escapeHtml(formatNumber.format(Math.round(peak)))}}</td></tr>`;
  }}).join('');
  const scroll=chart.parentElement,section=byId('concurrencySection'),isExpanded=section.classList.contains('expanded'),previousDayWidth=Number(scroll.dataset.dayWidth||0),visibleDay=previousDayWidth?Math.round(scroll.scrollLeft/previousDayWidth):0;
  const viewportWidth=Math.max(320,scroll.clientWidth||900),dayWidth=isExpanded?viewportWidth:Math.max(520,Math.min(680,viewportWidth/2.5)),width=Math.max(viewportWidth,dates.length*dayWidth),height=isExpanded?Math.max(420,window.innerHeight-116):255,top=20,bottom=58,left=12,right=12,innerHeight=height-top-bottom;
  const observed=points.map(point=>point.value),rawMin=observed.length?Math.min(...observed):0,rawMax=observed.length?Math.max(...observed):1,range=Math.max(1,rawMax-rawMin),stepSize=niceStep(range/6),axisMin=Math.max(0,Math.floor((rawMin-range*.08)/stepSize)*stepSize),axisMax=Math.max(axisMin+stepSize,Math.ceil((rawMax+range*.08)/stepSize)*stepSize),axisLabels=[],grid=[];
  for(let i=0;i<=6;i++){{const value=axisMin+(axisMax-axisMin)*i/6,y=top+innerHeight-((value-axisMin)/(axisMax-axisMin))*innerHeight;grid.push(`<line class="chart-grid" x1="${{left}}" x2="${{width-right}}" y1="${{y}}" y2="${{y}}"></line>`);axisLabels.push(`<span class="chart-y-axis-label" style="top:${{y}}px">${{escapeHtml(formatAxis(value))}}</span>`)}}
  axis.innerHTML=axisLabels.join('');
  const dateIndex=new Map(dates.map((date,index)=>[date,index])),dayInner=dayWidth-left-right;
  const xFor=point=>{{const index=dateIndex.get(point.date)||0;return index*dayWidth+left+(point.minuteOfDay/1440)*dayInner}},yFor=value=>top+innerHeight-((value-axisMin)/(axisMax-axisMin))*innerHeight;
  const labels=[],dayLines=[];
  dates.forEach((date,index)=>{{
    const dayStart=index*dayWidth;
    if(index>0)dayLines.push(`<line class="concurrency-day-line" x1="${{dayStart}}" x2="${{dayStart}}" y1="${{top}}" y2="${{top+innerHeight}}"></line>`);
    const hourTicks=isExpanded?Array.from({{length:25}},(_,hour)=>hour):[0,6,12,18,24];
    hourTicks.forEach(hour=>{{const x=dayStart+left+(hour/24)*dayInner,label=`${{pad(hour)}}:00`,anchor=hour===0?'start':hour===24?'end':'middle';labels.push(`<text class="chart-x-label" x="${{x}}" y="${{height-31}}" style="text-anchor:${{anchor}}">${{label}}</text>`)}});
    const dayLabel=new Date(`${{date}}T00:00:00`).toLocaleDateString('en-IN',{{weekday:'short',day:'2-digit',month:'short',year:'numeric'}});
    labels.push(`<text class="concurrency-day-label" x="${{dayStart+dayWidth/2}}" y="${{height-11}}">${{escapeHtml(dayLabel)}}</text>`);
  }});
  const paths=[],dots=[];let segment=[];
  const flush=()=>{{if(segment.length>1)paths.push(`<path class="concurrency-line" d="M ${{segment.map(point=>`${{xFor(point)}} ${{yFor(point.value)}}`).join(' L ')}}"></path>`);segment=[]}};
  points.forEach((point,index)=>{{const previous=points[index-1];if(previous&&point.time-previous.time>step*60000*1.5)flush();segment.push(point);if(index%Math.max(1,Math.round(15/step))===0)dots.push(`<circle class="concurrency-hover-dot" cx="${{xFor(point)}}" cy="${{yFor(point.value)}}" r="1.7"></circle>`)}});flush();
  chart.setAttribute('viewBox',`0 0 ${{width}} ${{height}}`);chart.style.width=`${{width}}px`;chart.style.minWidth=`${{width}}px`;chart.style.height=`${{height}}px`;axis.style.height=`${{height}}px`;scroll.dataset.dayWidth=String(dayWidth);
  chart.innerHTML=points.length?`${{grid.join('')}}${{dayLines.join('')}}<line class="chart-axis" x1="${{left}}" x2="${{width-right}}" y1="${{top+innerHeight}}" y2="${{top+innerHeight}}"></line>${{paths.join('')}}${{dots.join('')}}${{labels.join('')}}<line class="concurrency-hover-line" id="concurrencyHoverLine" y1="${{top}}" y2="${{top+innerHeight}}" hidden></line><circle class="concurrency-hover-dot" id="concurrencyHoverDot" r="4" hidden></circle><rect class="concurrency-hit-area" x="0" y="${{top}}" width="${{width}}" height="${{innerHeight}}"></rect>`:`<text class="chart-empty" x="18" y="120">No minute-level concurrency data for the selected filters</text>`;
  byId('concurrencyTotal').textContent=points.length?`Peak Users: ${{formatNumber.format(Math.round(rawMax))}} | ${{step===1?'1 min':'5 min'}}`:'No data';
  if(note)note.textContent=points.length?`Each point sums distinct cliIP counts for every minute inside the ${{step===1?'1 minute':'5 minute'}} bucket. Missing source minutes remain gaps.`:'No embedded minute-level cliIP rows for the selected filters.';
  const tooltip=byId('concurrencyTooltip');
  if(tooltip&&points.length){{
    const plotted=points.map((point,index)=>({{point,index,x:xFor(point),y:yFor(point.value)}})),hoverLine=byId('concurrencyHoverLine'),hoverDot=byId('concurrencyHoverDot'),hit=chart.querySelector('.concurrency-hit-area');
    const hide=()=>{{tooltip.style.display='none';hoverLine.setAttribute('hidden','');hoverDot.setAttribute('hidden','')}};
    hit.addEventListener('pointermove',event=>{{
      const bounds=chart.getBoundingClientRect(),cursorX=(event.clientX-bounds.left)*(width/bounds.width);
      let low=0,high=plotted.length-1;while(low<high){{const mid=Math.floor((low+high)/2);if(plotted[mid].x<cursorX)low=mid+1;else high=mid}}
      const candidates=[plotted[low],plotted[Math.max(0,low-1)]].filter(Boolean),hitPoint=candidates.reduce((best,item)=>!best||Math.abs(item.x-cursorX)<Math.abs(best.x-cursorX)?item:best,null);
      if(!hitPoint||Math.abs(hitPoint.x-cursorX)>Math.max(16,dayWidth/72)){{hide();return}}
      const point=hitPoint.point,previous=points[hitPoint.index-1];let change='';
      if(previous&&previous.date===point.date&&previous.value){{const percent=(point.value-previous.value)*100/Math.abs(previous.value);change=`<div class="tooltip-change">Change vs previous: ${{percent>=0?'+':''}}${{percent.toFixed(1)}}%</div>`}}
      tooltip.innerHTML=`<strong>${{escapeHtml(new Date(point.time).toLocaleString('en-IN',{{weekday:'short',day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit',hour12:true}}))}}</strong><div class="tooltip-value">Active viewers: ${{escapeHtml(formatNumber.format(Math.round(point.value)))}}</div>${{change}}`;
      tooltip.style.display='block';const tooltipWidth=tooltip.offsetWidth,tooltipHeight=tooltip.offsetHeight,tipX=Math.min(window.innerWidth-tooltipWidth-8,event.clientX+14),tipY=event.clientY-tooltipHeight-12;
      tooltip.style.left=`${{Math.max(8,tipX)}}px`;tooltip.style.top=`${{Math.max(8,tipY)}}px`;hoverLine.setAttribute('x1',hitPoint.x);hoverLine.setAttribute('x2',hitPoint.x);hoverDot.setAttribute('cx',hitPoint.x);hoverDot.setAttribute('cy',hitPoint.y);hoverLine.removeAttribute('hidden');hoverDot.removeAttribute('hidden');
    }});
    hit.addEventListener('pointerleave',hide);
  }}else if(tooltip)tooltip.style.display='none';
  requestAnimationFrame(()=>{{scroll.scrollLeft=Math.min(Math.max(0,visibleDay),Math.max(0,dates.length-1))*dayWidth}});
}}
function renderConcurrency(){{
  const chart=byId('concurrencyChart'),axis=byId('concurrencyChartYAxis'),body=byId('concurrencyDetailBody'),legend=byId('concurrencyLegend'),note=byId('concurrencyNote');
  const source=String(state.source||'').toLowerCase(),step=Number(byId('concurrencyResolution')?.value||1),channelTotal=channelsForSource(source).length,platformTotal=allPlatforms.length;
  const channelActive=state.channels.size>0&&state.channels.size<channelTotal,platformActive=source==='fast'&&state.platforms.size>0&&state.platforms.size<platformTotal;
  const selected=concurrencyRows.filter(row=>row[1]===source&&(!state.from||row[0]>=state.from)&&(!state.to||row[0]<=state.to)&&(!channelActive||state.channels.has(row[4]))&&(!platformActive||state.platforms.has(row[5])));
  const availableDates=unique(0).filter(date=>(!state.from||date>=state.from)&&(!state.to||date<=state.to)&&rows.some(row=>row[1]===source&&row[0]===date));
  const rangeStart=state.from||availableDates[0]||'',rangeEnd=state.to||availableDates.at(-1)||rangeStart,dates=[];
  if(rangeStart&&rangeEnd){{for(let cursor=new Date(`${{rangeStart}}T00:00:00Z`),last=new Date(`${{rangeEnd}}T00:00:00Z`);cursor<=last;cursor.setUTCDate(cursor.getUTCDate()+1))dates.push(cursor.toISOString().slice(0,10))}}
  const pad=value=>String(value).padStart(2,'0'),dateLabel=date=>new Date(`${{date}}T00:00:00`).toLocaleDateString('en-IN',{{day:'2-digit',month:'short'}});
  const parseMinute=value=>{{const match=String(value).match(/^([0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}) ([0-9]{{2}}):([0-9]{{2}})/);if(!match)return null;const minute=Math.floor(Number(match[3])/step)*step;return {{date:match[1],minuteOfDay:Number(match[2])*60+minute,key:`${{match[1]}} ${{match[2]}}:${{pad(minute)}}`}}}};
  const rawMinutes=new Map();
  selected.forEach(row=>{{const minute=parseMinute(row[2]);if(!minute)return;const exactKey=`${{minute.date}} ${{String(row[2]).slice(11,16)}}`;rawMinutes.set(exactKey,(rawMinutes.get(exactKey)||0)+Number(row[3]||0))}});
  const buckets=new Map();
  rawMinutes.forEach((value,key)=>{{const minute=parseMinute(key);if(!minute)return;const bucket=buckets.get(minute.key)||{{date:minute.date,minuteOfDay:minute.minuteOfDay,value:0}};bucket.value+=value;buckets.set(minute.key,bucket)}});
  const points=[...buckets.values()].sort((a,b)=>a.date.localeCompare(b.date)||a.minuteOfDay-b.minuteOfDay),series=new Map(dates.map(date=>[date,[]]));
  points.forEach(point=>{{if(series.has(point.date))series.get(point.date).push(point)}});
  body.innerHTML=dates.map(date=>{{const values=(series.get(date)||[]).map(point=>point.value),minuteSum=values.length?values.reduce((sum,value)=>sum+value,0):null,peak=values.length?Math.max(...values):null;return `<tr><td>${{escapeHtml(dateLabel(date))}}</td><td>${{minuteSum===null?'—':escapeHtml(formatNumber.format(Math.round(minuteSum)))}}</td><td>${{peak===null?'—':escapeHtml(formatNumber.format(Math.round(peak)))}}</td></tr>`}}).join('');
  const colors=['#0f766e','#2563eb','#d97706','#dc2626','#7c3aed','#059669','#be185d','#475569','#0891b2','#a16207','#4f46e5','#c2410c','#65a30d','#db2777','#92400e','#64748b','#1d4ed8','#0d9488','#b91c1c','#4d7c0f'],colorFor=new Map(dates.map((date,index)=>[date,colors[index%colors.length]]));
  legend.innerHTML=dates.map(date=>`<span class="concurrency-legend-item"><span class="concurrency-legend-swatch" style="background:${{colorFor.get(date)}}"></span>${{escapeHtml(dateLabel(date))}}</span>`).join('');
  const scroll=chart.parentElement,section=byId('concurrencySection'),isExpanded=section.classList.contains('expanded'),width=Math.max(320,scroll.clientWidth||900),height=isExpanded?Math.max(420,window.innerHeight-138):235,top=16,bottom=36,left=12,right=14,innerWidth=width-left-right,innerHeight=height-top-bottom;
  const observed=points.map(point=>point.value),rawMin=observed.length?Math.min(...observed):0,rawMax=observed.length?Math.max(...observed):1,range=Math.max(1,rawMax-rawMin),stepSize=niceStep(range/6),axisMin=Math.max(0,Math.floor((rawMin-range*.08)/stepSize)*stepSize),axisMax=Math.max(axisMin+stepSize,Math.ceil((rawMax+range*.08)/stepSize)*stepSize),axisLabels=[],grid=[];
  for(let i=0;i<=6;i++){{const value=axisMin+(axisMax-axisMin)*i/6,y=top+innerHeight-((value-axisMin)/(axisMax-axisMin))*innerHeight;grid.push(`<line class="chart-grid" x1="${{left}}" x2="${{width-right}}" y1="${{y}}" y2="${{y}}"></line>`);axisLabels.push(`<span class="chart-y-axis-label" style="top:${{y}}px">${{escapeHtml(formatAxis(value))}}</span>`)}}
  axis.innerHTML=axisLabels.join('');
  const xFor=minute=>left+(minute/1440)*innerWidth,yFor=value=>top+innerHeight-((value-axisMin)/(axisMax-axisMin))*innerHeight,hourGrid=[],labels=[];
  for(let hour=0;hour<=24;hour++){{const x=xFor(hour*60),anchor=hour===0?'start':hour===24?'end':'middle';hourGrid.push(`<line class="chart-grid" x1="${{x}}" x2="${{x}}" y1="${{top}}" y2="${{top+innerHeight}}" opacity=".55"></line>`);labels.push(`<text class="chart-x-label" x="${{x}}" y="${{height-10}}" style="text-anchor:${{anchor}}">${{pad(hour)}}</text>`)}}
  const paths=[];
  dates.forEach(date=>{{const datePoints=series.get(date)||[],color=colorFor.get(date);let segment=[];const flush=()=>{{if(segment.length>1)paths.push(`<path class="concurrency-line" style="stroke:${{color}}" d="M ${{segment.map(point=>`${{xFor(point.minuteOfDay)}} ${{yFor(point.value)}}`).join(' L ')}}"></path>`);segment=[]}};datePoints.forEach((point,index)=>{{const previous=datePoints[index-1];if(previous&&point.minuteOfDay-previous.minuteOfDay>step*1.5)flush();segment.push(point)}});flush()}});
  chart.setAttribute('viewBox',`0 0 ${{width}} ${{height}}`);chart.style.width='100%';chart.style.minWidth='0';chart.style.height=`${{height}}px`;axis.style.height=`${{height}}px`;
  chart.innerHTML=points.length?`${{grid.join('')}}${{hourGrid.join('')}}<line class="chart-axis" x1="${{left}}" x2="${{width-right}}" y1="${{top+innerHeight}}" y2="${{top+innerHeight}}"></line>${{paths.join('')}}${{labels.join('')}}<line class="concurrency-hover-line" id="concurrencyHoverLine" y1="${{top}}" y2="${{top+innerHeight}}" hidden></line><g id="concurrencyHoverDots"></g><rect class="concurrency-hit-area" x="${{left}}" y="${{top}}" width="${{innerWidth}}" height="${{innerHeight}}"></rect>`:`<text class="chart-empty" x="18" y="120">No minute-level concurrency data for the selected filters</text>`;
  byId('concurrencyTotal').textContent=points.length?`Peak Users: ${{formatNumber.format(Math.round(rawMax))}} | ${{step===1?'1 min':'5 min'}} | ${{dates.length}} day${{dates.length===1?'':'s'}}`:'No data';
  if(note)note.textContent=points.length?`Dates share the same 00–24 IST axis. Missing source minutes remain gaps.`:'No embedded minute-level cliIP rows for the selected filters.';
  const tooltip=byId('concurrencyTooltip');
  if(tooltip&&points.length){{
    const pointMaps=new Map(dates.map(date=>[date,new Map((series.get(date)||[]).map(point=>[point.minuteOfDay,point]))])),hoverLine=byId('concurrencyHoverLine'),hoverDots=byId('concurrencyHoverDots'),hit=chart.querySelector('.concurrency-hit-area');
    const hide=()=>{{tooltip.style.display='none';hoverLine.setAttribute('hidden','');hoverDots.innerHTML=''}};
    hit.addEventListener('pointermove',event=>{{const bounds=chart.getBoundingClientRect(),cursorX=(event.clientX-bounds.left)*(width/bounds.width),minute=Math.max(0,Math.min(1440,Math.round((((cursorX-left)/innerWidth)*1440)/step)*step)),entries=dates.map(date=>{{const point=pointMaps.get(date).get(minute);return point?{{date,point,color:colorFor.get(date)}}:null}}).filter(Boolean);if(!entries.length){{hide();return}}const x=xFor(minute);hoverLine.setAttribute('x1',x);hoverLine.setAttribute('x2',x);hoverLine.removeAttribute('hidden');hoverDots.innerHTML=entries.map(entry=>`<circle cx="${{x}}" cy="${{yFor(entry.point.value)}}" r="3.5" fill="#fff" stroke="${{entry.color}}" stroke-width="2"></circle>`).join('');tooltip.innerHTML=`<strong>${{pad(Math.floor(minute/60)%24)}}:${{pad(minute%60)}} IST</strong>${{entries.map(entry=>`<div class="tooltip-value"><span style="background:${{entry.color}}"></span>${{escapeHtml(dateLabel(entry.date))}}: ${{escapeHtml(formatNumber.format(Math.round(entry.point.value)))}}</div>`).join('')}}`;tooltip.style.display='block';const tooltipWidth=tooltip.offsetWidth,tooltipHeight=tooltip.offsetHeight,tipX=Math.min(window.innerWidth-tooltipWidth-8,event.clientX+14),tipY=event.clientY-tooltipHeight-12;tooltip.style.left=`${{Math.max(8,tipX)}}px`;tooltip.style.top=`${{Math.max(8,tipY)}}px`}});
    hit.addEventListener('pointerleave',hide);
  }}else if(tooltip)tooltip.style.display='none';
}}
const concurrencyObserver=new MutationObserver(renderConcurrency);concurrencyObserver.observe(byId('streamWatchDetailBody'),{{childList:true,subtree:true}});byId('concurrencyResolution').addEventListener('change',renderConcurrency);
const toggleConcurrencyExpand=force=>{{const section=byId('concurrencySection'),button=byId('concurrencyExpand'),expanded=typeof force==='boolean'?force:!section.classList.contains('expanded');section.classList.toggle('expanded',expanded);document.body.classList.toggle('chart-expanded',expanded);button.textContent=expanded?'Close':'Expand';button.setAttribute('aria-expanded',String(expanded));requestAnimationFrame(renderConcurrency)}};
byId('concurrencyExpand').addEventListener('click',()=>toggleConcurrencyExpand());document.addEventListener('keydown',event=>{{if(event.key==='Escape'&&byId('concurrencySection').classList.contains('expanded'))toggleConcurrencyExpand(false)}});let concurrencyResizeTimer;window.addEventListener('resize',()=>{{clearTimeout(concurrencyResizeTimer);concurrencyResizeTimer=setTimeout(renderConcurrency,120)}});renderConcurrency();
['streamWatchDetailBody','streamViewerDetailBody'].forEach(id=>new MutationObserver(refreshGraphHeaders).observe(byId(id),{{childList:true,subtree:true}}));
const cleanIdentityHeading=()=>{{const section=byId('streamIdentitySection');if(section)section.querySelector('.chart-title span').textContent='Device / Session IDs'}};new MutationObserver(cleanIdentityHeading).observe(byId('streamIdentityDetailBody'),{{childList:true,subtree:true}});cleanIdentityHeading();
const refreshIdentityTotal=()=>{{const body=byId('streamIdentityDetailBody'),section=byId('streamIdentitySection');if(!body||!section)return;let devices=0,sessions=0;body.querySelectorAll('tr').forEach(row=>{{devices+=Number(String(row.cells[1]?.textContent||'0').replace(/,/g,''))||0;sessions+=Number(String(row.cells[2]?.textContent||'0').replace(/,/g,''))||0}});const total=section.querySelector('.chart-total');if(total)total.textContent=`Total Devices: ${{formatNumber.format(devices)}} | Total Sessions: ${{formatNumber.format(sessions)}}`}};
const identityTotalObserver=new MutationObserver(refreshIdentityTotal);identityTotalObserver.observe(byId('streamIdentityDetailBody'),{{childList:true,subtree:true}});refreshIdentityTotal();
['streamWatchDetailScroll','streamViewerDetailScroll','streamIdentityDetailScroll'].forEach(id=>{{const detailScroll=byId(id);detailScroll.addEventListener('wheel',event=>{{event.stopImmediatePropagation()}},{{capture:true}})}});
</script>
</body>
</html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the standalone Phase 1 Watch Hours dashboard.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Canonical channel + geography daily Parquet mart.")
    parser.add_argument("--platform-input", type=Path, default=DEFAULT_PLATFORM_INPUT, help="FAST platform + channel geography Parquet mart.")
    parser.add_argument("--identity-input", type=Path, default=DEFAULT_IDENTITY_INPUT, help="Daily STREAM device/session identity Parquet mart.")
    parser.add_argument("--concurrency-input", type=Path, default=DEFAULT_CONCURRENCY_INPUT, help="Audience Ops identity-minute cliIP Parquet mart.")
    parser.add_argument("--ua-input", type=Path, default=DEFAULT_UA_INPUT, help="Source/channel scoped Device and OS daily Parquet mart.")
    parser.add_argument("--ua-source-input", type=Path, default=DEFAULT_UA_SOURCE_INPUT, help="Source-level UA daily Parquet used for true hierarchy relationships.")
    parser.add_argument("--ua-lookup-input", type=Path, default=DEFAULT_UA_LOOKUP_INPUT, help="Canonical decoded UA lookup Parquet.")
    parser.add_argument("--fast-ua-input", type=Path, default=DEFAULT_FAST_UA_INPUT, help="FAST platform/channel joint UA hierarchy Parquet.")
    parser.add_argument("--asn-input", type=Path, default=DEFAULT_ASN_INPUT, help="Source/date decoded ASN network Parquet.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT, help="Output standalone HTML path.")
    args = parser.parse_args()
    validate_input(args.input)
    rows = load_rows(args.input)
    platform_rows = load_platform_rows(args.platform_input)
    identity_rows = load_identity_rows(args.identity_input)
    dashboard_dates = sorted({str(row[0]) for row in rows})
    concurrency_rows = load_concurrency_rows(
        args.concurrency_input,
        dashboard_dates[0] if dashboard_dates else None,
        dashboard_dates[-1] if dashboard_dates else None,
    )
    ua_rows = load_ua_rows(
        args.ua_input,
        dashboard_dates[0] if dashboard_dates else None,
        dashboard_dates[-1] if dashboard_dates else None,
    )
    ua_hierarchy_rows = load_ua_hierarchy_rows(
        args.ua_source_input,
        args.ua_lookup_input,
        args.fast_ua_input,
        dashboard_dates[0] if dashboard_dates else None,
        dashboard_dates[-1] if dashboard_dates else None,
    )
    asn_rows = load_asn_rows(
        args.asn_input,
        dashboard_dates[0] if dashboard_dates else None,
        dashboard_dates[-1] if dashboard_dates else None,
    )
    publish_through = common_publish_through(
        rows,
        platform_rows,
        identity_rows,
        concurrency_rows,
        ua_rows,
        ua_hierarchy_rows,
        asn_rows,
    )
    rows = through_date(rows, publish_through)
    platform_rows = through_date(platform_rows, publish_through)
    identity_rows = through_date(identity_rows, publish_through)
    concurrency_rows = through_date(concurrency_rows, publish_through)
    ua_rows = through_date(ua_rows, publish_through)
    ua_hierarchy_rows = through_date(ua_hierarchy_rows, publish_through)
    asn_rows = through_date(asn_rows, publish_through)
    if not rows:
        raise ValueError(f"Input Parquet contains no usable rows: {args.input}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        render_html(rows, platform_rows, identity_rows, concurrency_rows, ua_rows, ua_hierarchy_rows, asn_rows),
        encoding="utf-8",
    )
    print(f"Wrote {args.out} through {publish_through} with {len(rows):,} aggregate rows.")


if __name__ == "__main__":
    main()

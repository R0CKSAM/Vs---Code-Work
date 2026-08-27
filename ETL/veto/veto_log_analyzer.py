#!/usr/bin/env python3
"""
VETO CDN Access Log Analyzer
=============================
Dynamic analyzer for Akamai-style CDN delivery logs in this schema:

    _folder, UA, asn, city, cliIP, country, queryStr, reqHost,
    reqPath, reqTimeSec, state

Two layers of metadata exist in this log format, with very different coverage:

1. ALWAYS PRESENT (derived from reqPath + UA on every row):
   content_id / year-month / episode_id / profile_id / filename
   -> file_type (manifest / segment), resolution
   platform (device family) + client app, guessed from the User-Agent string.

2. SOMETIMES PRESENT (only on rows where the player attached a query string,
   historically ~0.2% of rows -- varies by client/app version):
   session_id, device_id, category_name, platform, channel / channel_name,
   content_type, content_title, device, app_bundle, app_name.
   This is the ONLY source of real channel names / content titles / categories
   in this log format -- reqPath only contains opaque folder codes.

Because layer 2 coverage is sparse and not a random sample (some client
types never send it), every report this script prints states the coverage
% for anything derived from queryStr, so numbers are never presented as
more complete than they are.

Usage:
    python3 veto_log_analyzer.py export.csv
    python3 veto_log_analyzer.py export.csv --top 15 --out-dir ./out --json summary.json
    python3 veto_log_analyzer.py export.csv --chunksize 200000   # for very large files
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from urllib.parse import unquote, parse_qs

import pandas as pd
import numpy as np

pd.set_option("display.width", 160)

# ---------------------------------------------------------------------------
# Parsing helpers -- each is defensive against missing/malformed values,
# since real CDN logs always have some.
# ---------------------------------------------------------------------------

PLATFORM_RULES = [
    (re.compile(r"Apple TV", re.I), "Apple TV"),
    (re.compile(r"iPhone|iPad|iOS", re.I), "iOS"),
    (re.compile(r"Android.*(BRAVIA|AFT|SmartTV|GoogleTV|tv\b)", re.I), "Android TV / FireTV"),
    (re.compile(r"Android", re.I), "Android"),
    (re.compile(r"Windows", re.I), "Windows"),
    (re.compile(r"Mac OS X", re.I), "Mac"),
    (re.compile(r"Roku", re.I), "Roku"),
    (re.compile(r"SMART-TV|Tizen|SamsungBrowser", re.I), "Samsung TV"),
    (re.compile(r"WebOS", re.I), "LG TV"),
]

CLIENT_RE = re.compile(r"([A-Za-z][\w\.]*App[\w\.]*)/([\d.]+)")


def decode_ua(ua):
    if not isinstance(ua, str):
        return ""
    return unquote(ua)


def guess_platform(ua_decoded):
    for pattern, label in PLATFORM_RULES:
        if pattern.search(ua_decoded):
            return label
    if "AppleCoreMedia" in ua_decoded:
        return "Apple TV"
    return "Other"


def guess_client(ua_decoded):
    m = CLIENT_RE.search(ua_decoded)
    if m:
        return m.group(1)
    if "AppleCoreMedia" in ua_decoded:
        return "AppleCoreMedia"
    if "Dalvik" in ua_decoded:
        return "Dalvik/WebView"
    return "Other"


def parse_req_path(path):
    """
    Expected shape: {content_id}/{year}/{month}/{episode_id}/{profile_id}/{filename}
    Falls back gracefully for any shorter/irregular path.
    """
    if not isinstance(path, str) or not path:
        return {"content_id": None, "ym": None, "episode_id": None,
                "profile_id": None, "filename": None}
    parts = path.split("/")
    content_id = parts[0] if len(parts) > 0 else None
    ym = f"{parts[1]}-{parts[2]}" if len(parts) > 2 else None
    episode_id = parts[3] if len(parts) > 3 else None
    profile_id = parts[4] if len(parts) > 4 else None
    filename = parts[-1] if parts else None
    return {"content_id": content_id, "ym": ym, "episode_id": episode_id,
             "profile_id": profile_id, "filename": filename}


RES_RE = re.compile(r"_(\d{3,4}x\d{3,4})_?")


def classify_file(filename):
    if not isinstance(filename, str):
        return "other", None
    if filename.endswith(".m3u8"):
        return "manifest", ("master" if "master" in filename else None)
    m = RES_RE.search(filename)
    res = m.group(1) if m else None
    if filename.endswith(".ts"):
        return "segment(ts)", res
    if filename.endswith(".mp4"):
        return "segment(mp4)", res
    return "other", res


QS_FIELDS = ["session_id", "device_id", "category_name", "platform",
             "channel_name", "channel", "content_type", "content_title",
             "device", "app_bundle", "app_name", "app_store_url", "dnt"]


def parse_query_str(qs):
    if not isinstance(qs, str) or not qs:
        return {}
    try:
        d = {k: unquote(v[0]) for k, v in parse_qs(qs).items()}
    except Exception:
        return {}
    return {k: d.get(k) for k in QS_FIELDS if k in d}


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------

def enrich(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["ua_decoded"] = df["UA"].apply(decode_ua)
    df["platform_ua"] = df["ua_decoded"].apply(guess_platform)
    df["client"] = df["ua_decoded"].apply(guess_client)

    # Fast row-wise construction (avoids slow .apply(pd.Series))
    path_records = [parse_req_path(p) for p in df["reqPath"]]
    path_parts = pd.DataFrame.from_records(path_records, index=df.index)
    df = pd.concat([df, path_parts], axis=1)

    file_pairs = [classify_file(f) for f in df["filename"]]
    df["file_type"] = [x[0] for x in file_pairs]
    df["resolution"] = [x[1] for x in file_pairs]

    q_records = [parse_query_str(q) for q in df["queryStr"]]
    q_parts = pd.DataFrame.from_records(q_records, index=df.index)
    for f in QS_FIELDS:
        if f not in q_parts.columns:
            q_parts[f] = np.nan
    q_parts = q_parts.add_prefix("q_")
    df = pd.concat([df, q_parts], axis=1)

    # Best-available platform: prefer queryStr's explicit platform when present
    df["platform"] = df["q_platform"].where(df["q_platform"].notna(), df["platform_ua"])
    # Best-available channel / content type / title, only real when queryStr present
    df["channel"] = df["q_channel_name"].fillna(df["q_channel"])
    df["content_type"] = df["q_content_type"]
    df["content_title"] = df["q_content_title"].replace("null", np.nan)
    df["category"] = df["q_category_name"].replace(["null", "undefined"], np.nan)

    df["dt"] = pd.to_datetime(df["reqTimeSec"], unit="s", errors="coerce")
    df["hour"] = df["dt"].dt.hour
    df["state_clean"] = df["state"].apply(lambda s: unquote(s) if isinstance(s, str) else s)

    return df


def section(title):
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def coverage_note(df, col):
    n = df[col].notna().sum()
    pct = n / len(df) * 100 if len(df) else 0
    return f"(coverage: {n:,}/{len(df):,} rows, {pct:.2f}%)"


def top_counts(series, n):
    return series.value_counts().head(n)


def run_report(df: pd.DataFrame, top_n: int, out_dir: str | None, json_path: str | None):
    summary = {}

    section("OVERVIEW")
    total = len(df)
    viewers = df["cliIP"].nunique()
    print(f"Total requests:      {total:,}")
    print(f"Distinct client IPs: {viewers:,}")
    print(f"Countries:           {df['country'].nunique()}")
    print(f"Distinct episode IDs (path-derived): {df['episode_id'].nunique()}")
    print(f"Time window: {df['dt'].min()}  ->  {df['dt'].max()}")
    summary["overview"] = {
        "total_requests": int(total),
        "distinct_viewers": int(viewers),
        "countries": int(df["country"].nunique()),
        "episode_ids": int(df["episode_id"].nunique()),
        "window_start": str(df["dt"].min()),
        "window_end": str(df["dt"].max()),
    }

    section(f"PLATFORM  {coverage_note(df, 'platform')}")
    plat = top_counts(df["platform"], top_n)
    print(plat)
    summary["platform"] = plat.to_dict()

    seg = df[df["file_type"].astype(str).str.startswith("segment")]
    if len(seg):
        section("RESOLUTION MIX BY PLATFORM (% of that platform's segment requests)")
        ct = pd.crosstab(seg["platform"], seg["resolution"], normalize="index") * 100
        print(ct.round(1))
        summary["platform_resolution_pct"] = ct.round(1).to_dict(orient="index")

    section("TRAFFIC BY HOUR OF DAY (segment requests, server timestamp)")
    hourly = seg.groupby("hour").size().reindex(range(24), fill_value=0)
    print(hourly)
    summary["hourly_segment_requests"] = hourly.to_dict()

    section("GEOGRAPHY: TOP COUNTRIES")
    countries = top_counts(df["country"], top_n)
    print(countries)
    summary["top_countries"] = countries.to_dict()

    in_df = df[df["country"] == "IN"]
    if len(in_df):
        section("GEOGRAPHY: TOP STATES (India)")
        st = in_df.groupby("state_clean").agg(
            requests=("cliIP", "size"), viewers=("cliIP", "nunique")
        ).sort_values("requests", ascending=False).head(top_n)
        st["requests_per_viewer"] = (st["requests"] / st["viewers"]).round(1)
        print(st)
        summary["top_states_india"] = st.reset_index().to_dict(orient="records")

    section("NETWORK: TOP ISPs (ASN)")
    asn = df.groupby("asn").agg(
        requests=("cliIP", "size"), viewers=("cliIP", "nunique")
    ).sort_values("requests", ascending=False).head(top_n)
    print(asn)
    summary["top_asn"] = asn.reset_index().to_dict(orient="records")

    section("CONTENT: TOP EPISODE/ASSET IDs BY DELIVERY VOLUME (path-derived, opaque codes)")
    ep = seg.groupby("episode_id").agg(
        requests=("cliIP", "size"), viewers=("cliIP", "nunique")
    ).sort_values("requests", ascending=False).head(top_n)
    print(ep)
    summary["top_episode_ids"] = ep.reset_index().to_dict(orient="records")

    # --- queryStr-derived layer: only meaningful where it exists ---
    qs_cov = df["q_session_id"].notna().sum()
    section(f"RICH METADATA LAYER FROM queryStr  {coverage_note(df, 'q_session_id')}")
    if qs_cov == 0:
        print("No rows in this file carry a populated queryStr — channel/content-title/")
        print("category/session analysis is not possible for this export.")
    else:
        print("This is the ONLY source of channel name, content title, content type,")
        print("category, session_id and device_id in this log format. Numbers below")
        print("describe only the subset of traffic where a client happened to send it —")
        print("do not treat them as representative of total volume.\n")

        if df["channel"].notna().any():
            print("-- Channels --")
            ch = top_counts(df["channel"], top_n)
            print(ch)
            summary["channels"] = ch.to_dict()

        if df["content_type"].notna().any():
            print("\n-- Content type --")
            ctp = top_counts(df["content_type"], top_n)
            print(ctp)
            summary["content_type"] = ctp.to_dict()

        if df["category"].notna().any():
            print("\n-- Category --")
            cat = top_counts(df["category"], top_n)
            print(cat)
            summary["category"] = cat.to_dict()

        if df["content_title"].notna().any():
            print("\n-- Top content titles seen (by row count in this metadata subset) --")
            titles = top_counts(df["content_title"], top_n)
            print(titles)
            summary["content_titles"] = titles.to_dict()

        # crosswalk: path-derived episode_id -> real content_title, where both exist
        cw = df.loc[df["episode_id"].notna() & df["content_title"].notna(),
                     ["episode_id", "content_title", "channel"]].drop_duplicates("episode_id")
        if len(cw):
            print(f"\n-- episode_id -> content_title crosswalk ({len(cw)} of "
                  f"{df['episode_id'].nunique()} total episode IDs resolved) --")
            print(cw.head(top_n).to_string(index=False))
            summary["episode_title_crosswalk"] = cw.to_dict(orient="records")
            unresolved_top = [e for e in ep.index if e not in set(cw["episode_id"])]
            if unresolved_top:
                print(f"\nNote: {len(unresolved_top)} of the top {len(ep)} episodes by "
                      f"volume have NO title match in the metadata subset (their client "
                      f"type never sent queryStr) -- e.g. {unresolved_top[:5]}")

    if out_dir:
        import os
        os.makedirs(out_dir, exist_ok=True)
        plat.to_csv(f"{out_dir}/platform.csv")
        countries.to_csv(f"{out_dir}/top_countries.csv")
        asn.to_csv(f"{out_dir}/top_asn.csv")
        ep.to_csv(f"{out_dir}/top_episodes.csv")
        if len(in_df):
            st.to_csv(f"{out_dir}/top_states_india.csv")
        print(f"\nCSV breakdowns written to: {out_dir}/")

    if json_path:
        with open(json_path, "w") as f:
            json.dump(summary, f, indent=2, default=str)
        print(f"Full summary JSON written to: {json_path}")

    return summary


def main():
    ap = argparse.ArgumentParser(description="Analyze VETO-style CDN access logs.")
    ap.add_argument("csv_path", help="Path to the CDN log CSV")
    ap.add_argument("--top", type=int, default=10, help="Top-N rows per breakdown (default 10)")
    ap.add_argument("--out-dir", default=None, help="If set, write per-breakdown CSVs here")
    ap.add_argument("--json", dest="json_path", default=None, help="If set, write full summary JSON here")
    ap.add_argument("--chunksize", type=int, default=None,
                     help="Read/enrich in chunks of this many rows (for very large files)")
    args = ap.parse_args()

    if args.chunksize:
        chunks = []
        for chunk in pd.read_csv(args.csv_path, chunksize=args.chunksize):
            chunks.append(enrich(chunk))
        df = pd.concat(chunks, ignore_index=True)
    else:
        df = enrich(pd.read_csv(args.csv_path))

    run_report(df, args.top, args.out_dir, args.json_path)


if __name__ == "__main__":
    main()

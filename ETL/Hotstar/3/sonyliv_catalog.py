"""
sonyliv_catalog.py — scrape the SonyLIV sports catalog.

Target URL:  https://www.sonyliv.com/custompage/sports-2245
             (plus any sport sub-pages found during crawl)

Usage
-----
    # Full live crawl
    python sonyliv_catalog.py

    # Re-parse an existing raw JSONL (no browser needed)
    python sonyliv_catalog.py --raw sonyliv_raw.jsonl

    # Specific URLs
    python sonyliv_catalog.py --urls /sports/cricket /sports/football

Output columns (all in COMMON_COLUMNS from catalog_base):
    platform, rail, page, section,
    content_id, series_id, title, series_title, episode_title,
    content_type, content_subtype, is_live, description,
    year, release_date, rating, duration_sec, duration_label,
    season_number, episode_number, episode_count,
    sport, tournament, match_status, match_start_utc, teams,
    primary_genre, genre_tags, languages, original_language,
    available_languages, language_count,
    is_free, subscription_required, pay_per_view,
    found_in, detail_url, poster_url, scraped_at

How it works
------------
SonyLIV loads tray/asset data from two API shapes:
  Shape A — page-level tray list:
    GET https://apiv2.sonyliv.com/AGL/1.6/A/ENG/WEB/<country>/...
    Response: { resultObj: { containers: [ {title, uri, assets:{items:[...]}} ] } }

  Shape B — individual tray asset list (when user opens "View All"):
    Same structure, but nested deeper.

The Playwright browser intercepts both. We parse every JSON response whose URL
contains "sonyliv.com" or "apiv2.sonyliv.com".
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from catalog_base import (
    COMMON_COLUMNS, Browser, find_key, safe_get, save, secs
)

PLATFORM = "SonyLIV"
BASE     = "https://www.sonyliv.com"
API_BASE = "https://apiv2.sonyliv.com"

SPORTS_SEEDS = [
    "/custompage/sports-2245",
    "/sports/cricket",
    "/sports/football",
    "/sports/tennis",
    "/sports/wrestling",
    "/sports/kabaddi",
    "/sports/hockey",
    "/sports/badminton",
    "/sports/formula-e",
    "/sports/ufc",
    "/sports/golf",
    "/sports/chess",
]

# SonyLIV content type map (contentType field in API)
_CTYPE = {
    "EPISODE": "Episode",
    "MOVIE":   "Movie",
    "SERIES":  "Show",
    "CLIP":    "Clip",
    "TRAILER": "Trailer",
    "LIVE":    "Live",
    "MATCH":   "Match",
    "SPORT":   "Match",
    "EVENT":   "Match",
}

_SPORT_KEYWORDS = re.compile(
    r"cricket|football|soccer|tennis|kabaddi|hockey|badminton|"
    r"wrestling|wwe|ufc|mma|formula|f1|chess|golf|basketball|"
    r"volleyball|athletics|archery|boxing|kho.kho|shooting",
    re.I,
)


# ── row builder ───────────────────────────────────────────────────────────────

def _row(asset: dict, rail: str | None, page: str, section: str | None) -> dict | None:
    """Turn one SonyLIV asset dict into a flat row."""
    cid = (
        asset.get("contentId")
        or asset.get("id")
        or asset.get("assetId")
    )
    if not cid:
        return None

    title = (
        asset.get("title")
        or asset.get("episodeTitle")
        or asset.get("name")
        or ""
    ).strip()
    if not title:
        return None

    raw_type = (asset.get("contentType") or asset.get("assetType") or "").upper()
    ctype    = _CTYPE.get(raw_type, raw_type.title() or "Other")

    # Sport detection from genres / tags / title / rail
    genres_raw = (
        asset.get("genres")
        or asset.get("genre")
        or asset.get("tags")
        or []
    )
    if isinstance(genres_raw, str):
        genres_raw = [g.strip() for g in genres_raw.split(",")]
    genres = [str(g) for g in genres_raw if g]

    all_text = " ".join([title, rail or "", page, section or ""] + genres).lower()
    sport_m  = _SPORT_KEYWORDS.search(all_text)
    sport    = sport_m.group(0).title() if sport_m else None

    # Match metadata
    teams = (
        asset.get("teams")
        or asset.get("matchTitle")
        or asset.get("contestants")
    )
    if isinstance(teams, list):
        teams = " vs ".join(str(t.get("name", t)) for t in teams[:2])

    match_start = (
        asset.get("startTime")
        or asset.get("broadcastStartTime")
        or asset.get("scheduleTime")
    )

    # Access flags
    is_free = (
        asset.get("isFreeContent")
        or asset.get("isFree")
        or asset.get("accessType", "").upper() in ("FREE", "AVOD")
    )
    sub_req = not bool(is_free) if is_free is not None else None

    # Language
    langs = asset.get("languages") or asset.get("audioLanguages") or []
    if isinstance(langs, str):
        langs = [l.strip() for l in langs.split(",")]

    # Poster
    poster = (
        safe_get(asset, "thumbnails", "LANDSCAPE", "url")
        or safe_get(asset, "thumbnails", "PORTRAIT", "url")
        or safe_get(asset, "posterImageURL")
        or find_key(asset, "url")
    )

    detail = asset.get("webURL") or asset.get("uri") or asset.get("slug")
    if detail and not detail.startswith("http"):
        detail = BASE + ("/" + detail.lstrip("/"))

    return {
        "platform":             PLATFORM,
        "rail":                 rail,
        "page":                 page,
        "section":              section,
        "content_id":           str(cid),
        "series_id":            str(asset.get("seriesId") or ""),
        "title":                title,
        "series_title":         asset.get("showName") or asset.get("seriesTitle") or "",
        "episode_title":        asset.get("episodeTitle") or "",
        "content_type":         ctype,
        "content_subtype":      asset.get("subType") or asset.get("sportType") or "",
        "is_live":              bool(asset.get("isLive") or raw_type == "LIVE"),
        "description":          (asset.get("description") or "").strip(),
        "year":                 asset.get("releaseYear") or asset.get("year"),
        "release_date":         asset.get("broadcastDate") or asset.get("releaseDate"),
        "rating":               asset.get("certification") or asset.get("rating"),
        "duration_sec":         asset.get("duration") or secs(asset.get("durationLabel")),
        "duration_label":       asset.get("durationLabel") or asset.get("runTime"),
        "season_number":        asset.get("seasonNumber") or asset.get("season"),
        "episode_number":       asset.get("episodeNumber") or asset.get("episode"),
        "episode_count":        asset.get("episodeCount"),
        "sport":                sport,
        "tournament":           asset.get("tournament") or asset.get("seriesTitle"),
        "match_status":         asset.get("matchStatus") or asset.get("liveStatus"),
        "match_start_utc":      match_start,
        "teams":                teams,
        "primary_genre":        genres[0] if genres else None,
        "genre_tags":           ", ".join(genres),
        "languages":            ", ".join(langs),
        "original_language":    asset.get("originalLanguage") or (langs[0] if langs else None),
        "available_languages":  "; ".join(langs),
        "language_count":       len(langs) or None,
        "is_free":              bool(is_free),
        "subscription_required": sub_req,
        "pay_per_view":         bool(asset.get("isPayPerView") or asset.get("isPPV")),
        "found_in":             f"{page} > {rail or 'unknown'}",
        "detail_url":           detail,
        "poster_url":           poster,
    }


# ── response parser ───────────────────────────────────────────────────────────

class SonyLIVParser:
    def __init__(self):
        self.rows:    list[dict] = []
        self.seen:    set        = set()
        self._slugs:  set        = set()   # additional sport pages to crawl

    def parse(self, url: str, data: dict):
        if "sonyliv" not in url.lower():
            return

        # Infer page label from URL
        m    = re.search(r"sonyliv\.com(/[^?#]+)", url)
        page = m.group(1).strip("/").replace("-", " ").title() if m else "Sports"

        # Shape A/B: resultObj.containers[].assets.items[]
        containers = (
            safe_get(data, "resultObj", "containers")
            or safe_get(data, "data", "containers")
            or safe_get(data, "result", "containers")
            or []
        )
        if containers:
            for tray in containers:
                rail    = (tray.get("title") or tray.get("name") or "").strip() or None
                section = tray.get("uri") or tray.get("traySource")
                assets  = (
                    safe_get(tray, "assets", "items")
                    or tray.get("items")
                    or []
                )
                for asset in assets:
                    row = _row(asset, rail, page, section)
                    if row and self._add(row):
                        self.rows.append(row)
                # collect view-all slugs
                va = tray.get("uri") or find_key(tray, "nextOffsetURL")
                if va and str(va).startswith("/"):
                    self._slugs.add(va.split("?")[0])
            return

        # Flat items array (direct API response)
        items = (
            safe_get(data, "resultObj", "items")
            or safe_get(data, "data", "items")
            or safe_get(data, "result", "items")
            or []
        )
        for asset in items:
            row = _row(asset, None, page, None)
            if row and self._add(row):
                self.rows.append(row)

    def _add(self, row: dict) -> bool:
        key = (row["content_id"], row["rail"])
        if key in self.seen:
            return False
        self.seen.add(key)
        return True


# ── crawler ───────────────────────────────────────────────────────────────────

def crawl(
    seeds:    list[str] | None = None,
    out:      str = "sonyliv_sports.csv",
    raw_path: str = "sonyliv_raw.jsonl",
    append:   bool = True,
    delay:    float = 1.5,
) -> pd.DataFrame:
    parser  = SonyLIVParser()
    browser = Browser(parser.parse, raw_path=raw_path, append=append, delay=delay)
    browser.start()

    visited = set()
    queue   = list(seeds or SPORTS_SEEDS)

    try:
        while queue:
            slug = queue.pop(0)
            if slug in visited:
                continue
            visited.add(slug)
            url = BASE + slug if slug.startswith("/") else slug
            print(f"  visiting {slug} …")
            browser.visit(url, deep=True)
            print(f"    {len(parser.rows)} rows so far")
            # Enqueue any new sport sub-pages the parser found
            for s in parser._slugs - visited:
                queue.append(s)
            parser._slugs.clear()
    finally:
        browser.close()

    return save(parser.rows, out, COMMON_COLUMNS)


# ── re-parser ────────────────────────────────────────────────────────────────

def parse_file(raw_path: str, out: str = "sonyliv_sports.csv") -> pd.DataFrame:
    parser = SonyLIVParser()
    for line in open(raw_path, encoding="utf-8"):
        d = json.loads(line)
        parser.parse(d["url"], d["data"])
    return save(parser.rows, out, COMMON_COLUMNS)


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--urls",      nargs="*", help="extra slug(s) to crawl")
    ap.add_argument("--raw",       help="re-parse existing JSONL (no browser)")
    ap.add_argument("--save-raw",  default="sonyliv_raw.jsonl")
    ap.add_argument("--out",       default="sonyliv_sports.csv")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--delay",     type=float, default=1.5)
    a = ap.parse_args()

    if a.raw:
        parse_file(a.raw, a.out)
    else:
        seeds = (a.urls or []) + SPORTS_SEEDS
        crawl(seeds=seeds, out=a.out, raw_path=a.save_raw,
              append=not a.overwrite, delay=a.delay)

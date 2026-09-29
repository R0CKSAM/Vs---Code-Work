"""
zee5_catalog.py — scrape the ZEE5 sports catalog.

Target URL:  https://www.zee5.com/sports/games
             (plus sport sub-pages and live/upcoming sections)

Usage
-----
    python zee5_catalog.py

    python zee5_catalog.py --raw zee5_raw.jsonl    # re-parse saved file

How it works
------------
ZEE5 loads content through two API shapes:

  Shape A — page buckets (tray list):
    GET https://gwapi.zee5.com/content/tvod/showbucket
        ?bucket_id=<id>&translation=en&country=IN&...
    Response: { bucket_response: [ {bucket_name, items:[...]} ] }

  Shape B — individual content details:
    GET https://gwapi.zee5.com/content/details/
        show/<content_id>?...
    Response: { id, title, content_type, genres, ... }

  Shape C — search/listing:
    GET https://gwapi.zee5.com/content/list/...
    Response: { response: [ {id, title, ...} ] }

The browser intercepts all three.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd
from catalog_base import (
    COMMON_COLUMNS, Browser, find_key, safe_get, save, secs
)

PLATFORM = "ZEE5"
BASE     = "https://www.zee5.com"
API_BASE = "https://gwapi.zee5.com"

SPORTS_SEEDS = [
    "/sports/games",
    "/sports-games/cricket",
    "/sports-games/football",
    "/sports-games/tennis",
    "/sports-games/kabaddi",
    "/sports-games/hockey",
    "/sports-games/badminton",
    "/sports-games/wrestling",
    "/sports-games/athletics",
    "/sports-games/volleyball",
    "/live",         # live sports often here
]

_CTYPE = {
    "movie":         "Movie",
    "tvshow":        "Show",
    "episode":       "Episode",
    "clip":          "Clip",
    "trailer":       "Trailer",
    "live_event":    "Live",
    "match":         "Match",
    "sport":         "Match",
    "video":         "Clip",
    "music_video":   "Clip",
    "short_film":    "Movie",
    "web_series":    "Show",
    "original":      "Show",
}

_SPORT_RE = re.compile(
    r"cricket|football|soccer|tennis|kabaddi|hockey|badminton|"
    r"wrestling|wwe|ufc|mma|formula|chess|golf|basketball|"
    r"volleyball|athletics|archery|boxing|kho.kho|shooting|racing",
    re.I,
)


# ── row builder ───────────────────────────────────────────────────────────────

def _row(item: dict, rail: str | None, page: str, section: str | None) -> dict | None:
    cid = (
        item.get("id")
        or item.get("content_id")
        or item.get("asset_id")
    )
    if not cid:
        return None

    title = (
        item.get("title")
        or item.get("name")
        or item.get("show_title")
        or ""
    ).strip()
    if not title:
        return None

    raw_type = (
        item.get("content_type")
        or item.get("type")
        or item.get("asset_type")
        or ""
    ).lower()
    ctype = _CTYPE.get(raw_type, raw_type.title() or "Other")

    # Genres / tags
    genres_raw = (
        item.get("genres")
        or item.get("genre")
        or item.get("category")
        or []
    )
    if isinstance(genres_raw, str):
        genres_raw = [g.strip() for g in genres_raw.split(",")]
    genres = [str(g) for g in genres_raw if g]

    # Sport detection
    all_text = " ".join([title, rail or "", page, section or ""] + genres).lower()
    sport_m  = _SPORT_RE.search(all_text)
    sport    = sport_m.group(0).title() if sport_m else None

    # Match metadata
    teams = item.get("teams") or item.get("match_title") or item.get("contestants")
    if isinstance(teams, list):
        teams = " vs ".join(str(t.get("name", t) if isinstance(t, dict) else t) for t in teams[:2])

    match_start = (
        item.get("start_time")
        or item.get("broadcast_time")
        or item.get("schedule_time")
        or item.get("air_date")
    )

    # Language
    langs = item.get("languages") or item.get("audio_languages") or []
    if isinstance(langs, str):
        langs = [l.strip() for l in langs.split(",")]
    if not langs:
        lang_field = item.get("language") or item.get("original_language")
        if lang_field:
            langs = [lang_field]

    # Access
    is_free = (
        item.get("is_free")
        or item.get("isFree")
        or str(item.get("subscription_type", "")).upper() in ("FREE", "AVOD", "FVOD")
    )

    # Images
    images = item.get("images") or item.get("image_urls") or {}
    poster = (
        (images.get("landscape") if isinstance(images, dict) else None)
        or (images.get("portrait") if isinstance(images, dict) else None)
        or item.get("thumbnail_url")
        or item.get("image_url")
        or find_key(item, "url")
    )

    detail = item.get("permalink") or item.get("web_url") or item.get("url")
    if detail and not detail.startswith("http"):
        detail = BASE + ("/" + detail.lstrip("/"))

    return {
        "platform":             PLATFORM,
        "rail":                 rail,
        "page":                 page,
        "section":              section,
        "content_id":           str(cid),
        "series_id":            str(item.get("show_id") or item.get("series_id") or ""),
        "title":                title,
        "series_title":         item.get("show_title") or item.get("series_title") or "",
        "episode_title":        item.get("episode_title") or "",
        "content_type":         ctype,
        "content_subtype":      item.get("subtype") or item.get("sport_type") or "",
        "is_live":              bool(item.get("is_live") or raw_type == "live_event"),
        "description":          (item.get("description") or item.get("synopsis") or "").strip(),
        "year":                 item.get("release_year") or item.get("year"),
        "release_date":         item.get("release_date") or item.get("broadcast_date"),
        "rating":               item.get("age_rating") or item.get("certification"),
        "duration_sec":         item.get("duration") or secs(item.get("duration_label")),
        "duration_label":       item.get("duration_label") or item.get("run_time"),
        "season_number":        item.get("season_number") or item.get("season"),
        "episode_number":       item.get("episode_number") or item.get("episode"),
        "episode_count":        item.get("episode_count") or item.get("total_episodes"),
        "sport":                sport,
        "tournament":           item.get("tournament") or item.get("league") or item.get("series_title"),
        "match_status":         item.get("match_status") or item.get("live_status"),
        "match_start_utc":      match_start,
        "teams":                teams,
        "primary_genre":        genres[0] if genres else None,
        "genre_tags":           ", ".join(genres),
        "languages":            ", ".join(langs),
        "original_language":    item.get("original_language") or (langs[0] if langs else None),
        "available_languages":  "; ".join(langs),
        "language_count":       len(langs) or None,
        "is_free":              bool(is_free),
        "subscription_required": not bool(is_free) if is_free is not None else None,
        "pay_per_view":         bool(item.get("is_pay_per_view") or item.get("tvod")),
        "found_in":             f"{page} > {rail or 'unknown'}",
        "detail_url":           detail,
        "poster_url":           poster,
    }


# ── response parser ───────────────────────────────────────────────────────────

class ZEE5Parser:
    def __init__(self):
        self.rows:   list[dict] = []
        self.seen:   set        = set()
        self._slugs: set        = set()

    def parse(self, url: str, data: dict):
        if "zee5" not in url.lower():
            return

        m    = re.search(r"zee5\.com(/[^?#]+)", url)
        page = m.group(1).strip("/").replace("-", " ").replace("_", " ").title() if m else "Sports"

        # Shape A — bucket_response
        buckets = (
            safe_get(data, "bucket_response")
            or safe_get(data, "data", "buckets")
            or []
        )
        if buckets:
            for bucket in buckets:
                rail    = (bucket.get("bucket_name") or bucket.get("name") or "").strip() or None
                section = bucket.get("bucket_id") or bucket.get("id")
                items   = bucket.get("items") or bucket.get("assets") or []
                for item in items:
                    row = _row(item, rail, page, str(section) if section else None)
                    if row and self._add(row):
                        self.rows.append(row)
            return

        # Shape B — direct detail response
        if data.get("id") and data.get("title"):
            row = _row(data, None, page, None)
            if row and self._add(row):
                self.rows.append(row)
            return

        # Shape C — response list
        items = (
            safe_get(data, "response")
            or safe_get(data, "result")
            or safe_get(data, "data", "items")
            or safe_get(data, "items")
            or []
        )
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                row = _row(item, None, page, None)
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
    out:      str = "zee5_sports.csv",
    raw_path: str = "zee5_raw.jsonl",
    append:   bool = True,
    delay:    float = 1.5,
) -> pd.DataFrame:
    parser  = ZEE5Parser()
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
            for s in parser._slugs - visited:
                queue.append(s)
            parser._slugs.clear()
    finally:
        browser.close()

    return save(parser.rows, out, COMMON_COLUMNS)


def parse_file(raw_path: str, out: str = "zee5_sports.csv") -> pd.DataFrame:
    parser = ZEE5Parser()
    for line in open(raw_path, encoding="utf-8"):
        d = json.loads(line)
        parser.parse(d["url"], d["data"])
    return save(parser.rows, out, COMMON_COLUMNS)


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--urls",      nargs="*")
    ap.add_argument("--raw",       help="re-parse existing JSONL")
    ap.add_argument("--save-raw",  default="zee5_raw.jsonl")
    ap.add_argument("--out",       default="zee5_sports.csv")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--delay",     type=float, default=1.5)
    a = ap.parse_args()

    if a.raw:
        parse_file(a.raw, a.out)
    else:
        seeds = (a.urls or []) + SPORTS_SEEDS
        crawl(seeds=seeds, out=a.out, raw_path=a.save_raw,
              append=not a.overwrite, delay=a.delay)

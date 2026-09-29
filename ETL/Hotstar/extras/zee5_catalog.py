"""
zee5_catalog.py — scrape the ZEE5 sports catalog.  (AUDITED)

Target URL:  https://www.zee5.com/sports/games
             (plus sport sub-pages and the live section)

Usage
-----
    python zee5_catalog.py
    python zee5_catalog.py --raw zee5_raw.jsonl     # re-parse saved file
    python zee5_catalog.py --debug                 # log every JSON response (window visible by default)
    python zee5_catalog.py --headless              # hide the window — ZEE5 returned HTTP 403 to headless in testing

Response shapes handled (field names are from the original design notes and have NOT
been verified against live traffic — run with --debug and compare):
  A  bucket_response[] / data.buckets[]  →  {bucket_name, bucket_id, items[]}
  B  a single detail object              →  {id, title, ...}
  C  list payloads                       →  response[] / result[] / data.items[] / items[] / bare list
"""

from __future__ import annotations

import argparse
from urllib.parse import urlparse

import pandas as pd
from catalog_base import (
    COMMON_COLUMNS, BaseParser, Browser, absolute_url, as_str_list, as_text,
    detect_sport, duration_to_sec, first_present, parse_access, reparse,
    safe_get, save, teams_text, to_bool, to_utc_iso,
)

PLATFORM = "ZEE5"
BASE = "https://www.zee5.com"
API_BASE = "https://gwapi.zee5.com"

# NOTE: only /sports/games comes from the brief; the rest are guesses.
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
    "/live",
]

_CTYPE = {
    "movie":       "Movie",
    "tvshow":      "Show",
    "episode":     "Episode",
    "clip":        "Clip",
    "trailer":     "Trailer",
    "live_event":  "Live",
    "match":       "Match",
    "sport":       "Match",
    "video":       "Clip",
    "music_video": "Clip",
    "short_film":  "Movie",
    "web_series":  "Show",
    "original":    "Show",
}


# Hosts seen in a real run (--debug log) that carry site config / ads / plans / analytics,
# not catalogue content. Their JSON is ignored by the parser.
NON_CONTENT_HOSTS = {
    "stcf-prod.zee5.com",        # menu.json, payload rules, remote config
    "cerberus.zee5.com",         # platform config
    "event-prod.zee5.com",       # analytics events
    "subscriptionapiv2.zee5.com",  # purchase plans
    "spapi.zee5.com",            # display-ads playback config
}


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def is_zee5_host(url: str) -> bool:
    h = _host(url)
    return h == "zee5.com" or h.endswith(".zee5.com")


def is_content_url(url: str) -> bool:
    return is_zee5_host(url) and _host(url) not in NON_CONTENT_HOSTS


# ── row builder ──────────────────────────────────────────────────────────────

def _row(item: dict, rail: str | None, page: str, section: str | None) -> dict | None:
    if not isinstance(item, dict):
        return None
    cid = first_present(item.get("id"), item.get("content_id"), item.get("asset_id"))
    if cid is None:
        return None
    title = as_text(first_present(item.get("title"), item.get("name"), item.get("show_title")))
    if not title:
        return None

    raw_type = as_text(first_present(item.get("content_type"), item.get("type"),
                                     item.get("asset_type"))).lower()
    ctype = _CTYPE.get(raw_type, raw_type.title() or "Other")

    genres = as_str_list(first_present(item.get("genres"), item.get("genre"), item.get("category")))
    sport, sport_src = detect_sport(genres, title, rail, page, section)

    langs = as_str_list(first_present(item.get("languages"), item.get("audio_languages")))
    original_lang = as_text(item.get("original_language")) or None
    if not langs:
        single = as_text(item.get("language")) or original_lang
        if single:
            langs = [single]

    is_free, sub_req, ppv = parse_access(
        free_flag=first_present(item.get("is_free"), item.get("isFree")),
        mode=first_present(item.get("subscription_type"), item.get("business_type")),
        ppv_flag=first_present(item.get("is_pay_per_view"), item.get("tvod")),
    )

    images = item.get("images") or item.get("image_urls")
    if not isinstance(images, dict):
        images = {}
    poster = first_present(images.get("landscape"), images.get("portrait"),
                           item.get("thumbnail_url"), item.get("image_url"))

    duration_label = first_present(item.get("duration_label"), item.get("run_time"))
    tournament = as_text(first_present(item.get("tournament"), item.get("league"),
                                       item.get("series_title"))) or None
    live_flag = to_bool(item.get("is_live"))

    return {
        "platform":              PLATFORM,
        "rail":                  rail,
        "page":                  page,
        "section":               section,
        "content_id":            str(cid),
        "series_id":             as_text(first_present(item.get("show_id"), item.get("series_id"))),
        "title":                 title,
        "series_title":          as_text(first_present(item.get("show_title"), item.get("series_title"))),
        "episode_title":         as_text(item.get("episode_title")),
        "content_type":          ctype,
        "content_subtype":       as_text(first_present(item.get("subtype"), item.get("sport_type"))),
        "is_live":               bool(live_flag) or raw_type == "live_event",
        "description":           as_text(first_present(item.get("description"), item.get("synopsis"))),
        "year":                  first_present(item.get("release_year"), item.get("year")),
        "release_date":          first_present(item.get("release_date"), item.get("broadcast_date")),
        "rating":                first_present(item.get("age_rating"), item.get("certification")),
        "duration_sec":          duration_to_sec(item.get("duration"), duration_label),
        "duration_label":        duration_label,
        "season_number":         first_present(item.get("season_number"), item.get("season")),
        "episode_number":        first_present(item.get("episode_number"), item.get("episode")),
        "episode_count":         first_present(item.get("episode_count"), item.get("total_episodes")),
        "sport":                 sport,
        "sport_source":          sport_src,
        "tournament":            tournament,
        "match_status":          first_present(item.get("match_status"), item.get("live_status")),
        "match_start_utc":       to_utc_iso(first_present(
                                     item.get("start_time"), item.get("broadcast_time"),
                                     item.get("schedule_time"), item.get("air_date"))),
        "teams":                 teams_text(first_present(
                                     item.get("teams"), item.get("match_title"),
                                     item.get("contestants"))),
        "primary_genre":         genres[0] if genres else None,
        "genre_tags":            ", ".join(genres),
        "languages":             ", ".join(langs),
        "original_language":     original_lang,          # never guessed from the language list
        "available_languages":   "; ".join(langs),
        "language_count":        len(langs) or None,
        "is_free":               is_free,
        "subscription_required": sub_req,
        "pay_per_view":          ppv,
        "found_in":              f"{page} > {rail or '(no rail)'}",
        "detail_url":            absolute_url(first_present(
                                     item.get("permalink"), item.get("web_url"), item.get("url")), BASE),
        "poster_url":            poster,
    }


# ── response parser ──────────────────────────────────────────────────────────

class ZEE5Parser(BaseParser):
    def parse(self, url: str, data):
        if not is_content_url(url):
            return
        page = self.page_for(url)

        # bare list → Shape C
        if isinstance(data, list):
            self._items(data, None, page, None)
            return
        if not isinstance(data, dict):
            return

        # Shape A — buckets
        buckets = first_present(data.get("bucket_response"), safe_get(data, "data", "buckets"))
        if isinstance(buckets, dict):
            buckets = [buckets]
        if isinstance(buckets, list) and buckets:
            for b in buckets:
                if not isinstance(b, dict):
                    continue
                rail = as_text(first_present(b.get("bucket_name"), b.get("name"))) or None
                section = first_present(b.get("bucket_id"), b.get("id"))
                items = first_present(b.get("items"), b.get("assets")) or []
                self._items(items, rail, page, str(section) if section is not None else None)
                self.maybe_slug(first_present(b.get("view_all_url"), b.get("link")))
            return

        # Shape B — a single detail object
        if "id" in data and "title" in data:
            self.add(_row(data, None, page, None))
            return

        # Shape C — list under a known key
        items = first_present(data.get("response"), data.get("result"),
                              safe_get(data, "data", "items"), data.get("items"))
        if isinstance(items, list):
            self._items(items, None, page, None)

    def _items(self, items, rail, page, section):
        if not isinstance(items, list):
            return
        for it in items:
            self.add(_row(it, rail, page, section))


# ── crawler / re-parser ──────────────────────────────────────────────────────

def crawl(seeds: list[str] | None = None, out: str = "zee5_sports.csv",
          raw_path: str = "zee5_raw.jsonl", append: bool = True, delay: float = 1.5,
          headed: bool = True, headless_new: bool = True, debug: bool = False,
          max_pages: int = 40) -> pd.DataFrame:
    parser = ZEE5Parser()
    browser = Browser(parser.parse, raw_path=raw_path, append=append,
                      delay=delay, headed=headed, debug=debug, headless_new=headless_new, raw_filter=is_zee5_host)
    browser.start()
    visited: set = set()
    blocked_streak = 0
    queue = list(seeds or SPORTS_SEEDS)
    try:
        while queue and len(visited) < max_pages:
            slug = queue.pop(0)
            if slug in visited:
                continue
            visited.add(slug)
            url = slug if slug.startswith("http") else BASE + slug
            parser.current_page = browser.current_page = slug
            before = len(parser.rows)
            browser.blocked_docs = 0
            print(f"  visiting {slug} …")
            browser.visit(url, deep=True)
            print(f"    +{len(parser.rows) - before} rows ({len(parser.rows)} total, "
                  f"{browser.n_json} JSON responses)")
            if browser.blocked_docs and len(parser.rows) == before:
                blocked_streak += 1
                if blocked_streak >= 2:
                    print("  ✗ ZEE5 is rejecting this browser (HTTP 403 on pages). Stopping early.\n"
                          "    Run with a visible window (default) — headless mode is commonly blocked.")
                    break
            else:
                blocked_streak = 0
            for href in browser.page_links():          # discover real sport pages from the DOM
                parser.maybe_slug(href)
            for s in sorted(parser.slugs - visited):
                if s not in queue:
                    queue.append(s)
            parser.slugs.clear()
    finally:
        browser.close()
    if browser.n_json == 0:
        print("  ⚠  no JSON responses captured at all — likely blocked or wrong URL.")
    return save(parser.rows, out, COMMON_COLUMNS, platform=PLATFORM)


def parse_file(raw_path: str, out: str = "zee5_sports.csv") -> pd.DataFrame:
    parser = ZEE5Parser()
    reparse(parser, raw_path)
    return save(parser.rows, out, COMMON_COLUMNS, platform=PLATFORM)


# ── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--urls", nargs="*", help="extra slug(s) to crawl")
    ap.add_argument("--raw", help="re-parse existing JSONL (no browser)")
    ap.add_argument("--save-raw", default="zee5_raw.jsonl")
    ap.add_argument("--out", default="zee5_sports.csv")
    ap.add_argument("--overwrite", action="store_true", help="overwrite raw JSONL instead of appending")
    ap.add_argument("--delay", type=float, default=1.5)
    ap.add_argument("--headless", action="store_true",
                    help="hide the browser window (ZEE5 may answer 403 to headless browsers)")
    ap.add_argument("--headed", action="store_true", help=argparse.SUPPRESS)   # kept for old commands
    ap.add_argument("--debug", action="store_true", help="log every JSON response")
    ap.add_argument("--max-pages", type=int, default=40)
    a = ap.parse_args()

    if a.raw:
        parse_file(a.raw, a.out)
    else:
        crawl(seeds=(a.urls or []) + SPORTS_SEEDS, out=a.out, raw_path=a.save_raw,
              append=not a.overwrite, delay=a.delay, headed=not a.headless, headless_new=True,
              debug=a.debug, max_pages=a.max_pages)

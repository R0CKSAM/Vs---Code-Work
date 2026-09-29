"""
sonyliv_catalog.py — scrape the SonyLIV sports catalog.  (AUDITED)

Target URL:  https://www.sonyliv.com/custompage/sports-2245
             (plus sport sub-pages found during the crawl)

Usage
-----
    python sonyliv_catalog.py                      # full live crawl
    python sonyliv_catalog.py --raw sonyliv_raw.jsonl   # re-parse, no browser
    python sonyliv_catalog.py --urls /sports/cricket    # extra pages
    python sonyliv_catalog.py --debug                  # log every JSON response (window visible by default)

Response shapes handled (field names are from the original design notes and have NOT
been verified against live traffic — run with --debug and compare):
  A/B  resultObj.containers[].assets.items[]   (containers may nest)
  C    flat items: resultObj.items / data.items / result.items / bare list
"""

from __future__ import annotations

import argparse
import re
from urllib.parse import urlparse

import pandas as pd
from catalog_base import (
    COMMON_COLUMNS, BaseParser, Browser, absolute_url, as_str_list, as_text,
    detect_sport, duration_to_sec, first_present, parse_access, reparse,
    safe_get, save, teams_text, to_bool, to_utc_iso,
)

PLATFORM = "SonyLIV"
BASE = "https://www.sonyliv.com"
API_BASE = "https://apiv2.sonyliv.com"

# NOTE: only /custompage/sports-2245 comes from the brief; the rest are guesses.
# A page that doesn't exist just yields nothing — check the crawl log.
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


def is_sonyliv_host(url: str) -> bool:
    h = (urlparse(url).hostname or "").lower()
    return h == "sonyliv.com" or h.endswith(".sonyliv.com")


# ── row builder ──────────────────────────────────────────────────────────────

def _row(asset: dict, rail: str | None, page: str, section: str | None) -> dict | None:
    if not isinstance(asset, dict):
        return None
    cid = first_present(asset.get("contentId"), asset.get("id"), asset.get("assetId"))
    if cid is None:
        return None
    title = as_text(first_present(asset.get("title"), asset.get("episodeTitle"), asset.get("name")))
    if not title:
        return None

    raw_type = as_text(first_present(asset.get("contentType"), asset.get("assetType"))).upper()
    ctype = _CTYPE.get(raw_type, raw_type.title() or "Other")

    genres = as_str_list(first_present(asset.get("genres"), asset.get("genre"), asset.get("tags")))
    sport, sport_src = detect_sport(genres, title, rail, page, section)

    is_free, sub_req, ppv = parse_access(
        free_flag=first_present(asset.get("isFreeContent"), asset.get("isFree")),
        mode=first_present(asset.get("accessType"), asset.get("subscriptionType")),
        ppv_flag=first_present(asset.get("isPayPerView"), asset.get("isPPV")),
    )

    langs = as_str_list(first_present(asset.get("languages"), asset.get("audioLanguages")))
    poster = (
        safe_get(asset, "thumbnails", "LANDSCAPE", "url")
        or safe_get(asset, "thumbnails", "PORTRAIT", "url")
        or asset.get("posterImageURL")
    )
    duration_label = first_present(asset.get("durationLabel"), asset.get("runTime"))
    tournament = as_text(first_present(asset.get("tournament"), asset.get("seriesTitle"))) or None
    live_flag = to_bool(asset.get("isLive"))

    return {
        "platform":              PLATFORM,
        "rail":                  rail,
        "page":                  page,
        "section":               section,
        "content_id":            str(cid),
        "series_id":             as_text(asset.get("seriesId")),
        "title":                 title,
        "series_title":          as_text(first_present(asset.get("showName"), asset.get("seriesTitle"))),
        "episode_title":         as_text(asset.get("episodeTitle")),
        "content_type":          ctype,
        "content_subtype":       as_text(first_present(asset.get("subType"), asset.get("sportType"))),
        "is_live":               bool(live_flag) or raw_type == "LIVE",
        "description":           as_text(asset.get("description")),
        "year":                  first_present(asset.get("releaseYear"), asset.get("year")),
        "release_date":          first_present(asset.get("broadcastDate"), asset.get("releaseDate")),
        "rating":                first_present(asset.get("certification"), asset.get("rating")),
        "duration_sec":          duration_to_sec(asset.get("duration"), duration_label),
        "duration_label":        duration_label,
        "season_number":         first_present(asset.get("seasonNumber"), asset.get("season")),
        "episode_number":        first_present(asset.get("episodeNumber"), asset.get("episode")),
        "episode_count":         asset.get("episodeCount"),
        "sport":                 sport,
        "sport_source":          sport_src,
        "tournament":            tournament,
        "match_status":          first_present(asset.get("matchStatus"), asset.get("liveStatus")),
        "match_start_utc":       to_utc_iso(first_present(
                                     asset.get("startTime"), asset.get("broadcastStartTime"),
                                     asset.get("scheduleTime"))),
        "teams":                 teams_text(first_present(
                                     asset.get("teams"), asset.get("matchTitle"),
                                     asset.get("contestants"))),
        "primary_genre":         genres[0] if genres else None,
        "genre_tags":            ", ".join(genres),
        "languages":             ", ".join(langs),
        "original_language":     as_text(asset.get("originalLanguage")) or None,   # never guessed
        "available_languages":   "; ".join(langs),
        "language_count":        len(langs) or None,
        "is_free":               is_free,
        "subscription_required": sub_req,
        "pay_per_view":          ppv,
        "found_in":              f"{page} > {rail or '(no rail)'}",
        "detail_url":            absolute_url(first_present(
                                     asset.get("webURL"), asset.get("uri"), asset.get("slug")), BASE),
        "poster_url":            poster,
    }


# ── response parser ──────────────────────────────────────────────────────────

class SonyLIVParser(BaseParser):
    def parse(self, url: str, data):
        if not is_sonyliv_host(url):
            return
        page = self.page_for(url)

        if isinstance(data, list):
            self._items(data, None, page, None)
            return
        if not isinstance(data, dict):
            return

        containers = first_present(
            safe_get(data, "resultObj", "containers"),
            safe_get(data, "data", "containers"),
            safe_get(data, "result", "containers"),
        )
        if isinstance(containers, list):
            for tray in containers:
                self._tray(tray, page, depth=0)
            return

        items = first_present(
            safe_get(data, "resultObj", "items"),
            safe_get(data, "data", "items"),
            safe_get(data, "result", "items"),
        )
        if isinstance(items, list):
            self._items(items, None, page, None)

    def _tray(self, tray, page: str, depth: int):
        if not isinstance(tray, dict) or depth > 5:
            return
        rail = as_text(first_present(tray.get("title"), tray.get("name"))) or None
        section = as_text(first_present(tray.get("uri"), tray.get("traySource"))) or None
        assets = first_present(safe_get(tray, "assets", "items"), tray.get("items")) or []
        self._items(assets, rail, page, section)
        self.maybe_slug(tray.get("uri"))
        nested = tray.get("containers")
        if isinstance(nested, list):
            for t in nested:
                self._tray(t, page, depth + 1)

    def _items(self, assets, rail, page, section):
        if not isinstance(assets, list):
            return
        for a in assets:
            self.add(_row(a, rail, page, section))


# ── crawler / re-parser ──────────────────────────────────────────────────────

def crawl(seeds: list[str] | None = None, out: str = "sonyliv_sports.csv",
          raw_path: str = "sonyliv_raw.jsonl", append: bool = True, delay: float = 1.5,
          headed: bool = True, headless_new: bool = True, debug: bool = False,
          max_pages: int = 40) -> pd.DataFrame:
    parser = SonyLIVParser()
    browser = Browser(parser.parse, raw_path=raw_path, append=append,
                      delay=delay, headed=headed, debug=debug, headless_new=headless_new, raw_filter=is_sonyliv_host)
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
                    print("  ✗ SonyLIV is rejecting this browser (HTTP 403 on pages). Stopping early.\n"
                          "    Run with a visible window (default) — headless mode is commonly blocked.")
                    break
            else:
                blocked_streak = 0
            for href in browser.page_links():
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


def parse_file(raw_path: str, out: str = "sonyliv_sports.csv") -> pd.DataFrame:
    parser = SonyLIVParser()
    reparse(parser, raw_path)
    return save(parser.rows, out, COMMON_COLUMNS, platform=PLATFORM)


# ── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--urls", nargs="*", help="extra slug(s) to crawl")
    ap.add_argument("--raw", help="re-parse existing JSONL (no browser)")
    ap.add_argument("--save-raw", default="sonyliv_raw.jsonl")
    ap.add_argument("--out", default="sonyliv_sports.csv")
    ap.add_argument("--overwrite", action="store_true", help="overwrite raw JSONL instead of appending")
    ap.add_argument("--delay", type=float, default=1.5)
    ap.add_argument("--headless", action="store_true",
                    help="hide the browser window (sites often answer 403 to headless browsers)")
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

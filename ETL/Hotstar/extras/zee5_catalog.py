"""
zee5_catalog.py — scrape the ZEE5 sports catalog.  (AUDITED + REAL-SHAPE v3)

Verified against a live capture:
  GraphQL /artemis CCQ page:    data.collection.rails[]  → each rail: {title, contents:[...]}
  GraphQL /artemis Guide:       data.programGuide[]      → each entry: {title, contents:[...]}
  Legacy / flat payloads        bucket_response[] / data.buckets[] / response[] / items[] / bare list

Seeds:  only /sports/games is verified against the brief.  Wrong guesses redirect to
generic landing pages ("Family Time with KidZ", general Live TV).  Those rows are
pruned once after the crawl by crawl() — not by _row(), which stays pure.
"""
from __future__ import annotations

import argparse
import json
import re
from urllib.parse import urlparse

import pandas as pd
from catalog_base import (
    COMMON_COLUMNS, BaseParser, Browser, absolute_url, all_text_fields, as_str_list, as_text,
    detect_sport, duration_to_sec, first_present, parse_access, reparse,
    safe_get, save, teams_text, to_bool, to_utc_iso,
)

PLATFORM = "ZEE5"
BASE = "https://www.zee5.com"
API_BASE = "https://gwapi.zee5.com"

# /live is general Live TV (Zee TV, Zee Cinema…) — deliberately removed.
SPORTS_SEEDS = [
    "/sports/games",
    "/sports-games/cricket",
    "/sports-games/football",
    "/sports-games/kabaddi",
]

_CTYPE = {
    "movie": "Movie", "tvshow": "Show", "episode": "Episode",
    "clip": "Clip", "trailer": "Trailer", "live_event": "Live",
    "match": "Match", "sport": "Match", "video": "Clip",
    "music_video": "Clip", "short_film": "Movie", "web_series": "Show",
    "original": "Show",
}
_TYPENAME_MAP = {
    "livetvchannel": "Live", "episode": "Episode", "movie": "Movie",
    "tvshow": "Show", "show": "Show", "clip": "Clip", "match": "Match",
    "trailer": "Trailer",
}
_ASSET_TYPE_MAP = {
    1: "Movie", 6: "Show", 8: "Show", 9: "Live", 10: "Live", 11: "Other",
}
_LANG_NAME = {
    "hi": "Hindi", "en": "English", "ta": "Tamil", "te": "Telugu",
    "ml": "Malayalam", "kn": "Kannada", "bn": "Bengali", "mr": "Marathi",
    "gu": "Gujarati", "pa": "Punjabi", "or": "Odia", "as": "Assamese",
    "ur": "Urdu", "bho": "Bhojpuri",
}

_SPORTS_PAGE_RE = re.compile(r"sport|game|match|cricket|football|kabaddi|tennis|"
                             r"hockey|badminton|wrestl|athletic", re.I)


def _lang_names(codes):
    out = []
    for c in codes or []:
        key = str(c).strip().lower()
        n = _LANG_NAME.get(key, str(c).strip())
        if n and n not in out:
            out.append(n)
    return out


def _is_sports_page(page: str | None) -> bool:
    return bool(page and _SPORTS_PAGE_RE.search(page))


NON_CONTENT_HOSTS = {
    "stcf-prod.zee5.com", "cerberus.zee5.com", "event-prod.zee5.com",
    "subscriptionapiv2.zee5.com", "spapi.zee5.com",
}


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def is_zee5_host(url: str) -> bool:
    h = _host(url)
    return h == "zee5.com" or h.endswith(".zee5.com")


def is_content_url(url: str) -> bool:
    return is_zee5_host(url) and _host(url) not in NON_CONTENT_HOSTS


# ── row builder (pure — no crawl-time policy) ────────────────────────────────

def _row(item: dict, rail: str | None, page: str, section: str | None) -> dict | None:
    if not isinstance(item, dict):
        return None
    cid = first_present(item.get("id"), item.get("content_id"), item.get("asset_id"))
    if cid is None:
        return None
    title = as_text(first_present(item.get("title"), item.get("name"),
                                  item.get("show_title"), item.get("originalTitle")))
    if not title:
        return None

    raw_type = as_text(first_present(item.get("content_type"), item.get("type"),
                                     item.get("asset_type"))).lower()
    typename = as_text(item.get("__typename")).lower()
    atype = item.get("assetType")
    ctype = (_CTYPE.get(raw_type)
             or _TYPENAME_MAP.get(typename)
             or (_ASSET_TYPE_MAP.get(atype) if isinstance(atype, int) else None)
             or (raw_type.title() if raw_type else None)
             or "Other")

    genres = as_str_list(first_present(item.get("genres"), item.get("genre"),
                                       item.get("category"), item.get("category_name")))
    sport, sport_src = detect_sport(genres, title, rail, page, section)

    category = as_text(first_present(item.get("category"), item.get("category_name"),
                                     item.get("primary_category"), item.get("categoryName"))) or None
    subcategory = as_text(first_present(item.get("subcategory"), item.get("sub_category"),
                                        item.get("secondary_category"), item.get("sub_genre"))) or None
    tags = as_str_list(first_present(item.get("tags"), item.get("tag_list"),
                                     item.get("keywords"), item.get("content_tags")))

    langs_raw = as_str_list(first_present(item.get("languages"),
                                          item.get("audio_languages"),
                                          item.get("audioLanguages")))
    langs = _lang_names(langs_raw)
    original_lang = as_text(first_present(item.get("original_language"),
                                          item.get("originalLanguage"))) or None
    if not langs:
        single = as_text(item.get("language")) or original_lang
        if single:
            langs = [single]

    is_free, sub_req, ppv = parse_access(
        free_flag=first_present(item.get("is_free"), item.get("isFree")),
        mode=first_present(item.get("subscription_type"), item.get("subscriptionType"),
                           item.get("business_type"), item.get("businessType")),
        ppv_flag=first_present(item.get("is_pay_per_view"), item.get("isPayPerView"),
                               item.get("tvod")),
    )

    images = item.get("images") or item.get("image_urls")
    if not isinstance(images, dict):
        images = {}
    poster = first_present(images.get("landscape"), images.get("portrait"),
                           item.get("thumbnail_url"), item.get("image_url"))

    duration_label = first_present(item.get("duration_label"), item.get("run_time"))
    tournament = as_text(first_present(item.get("tournament"), item.get("league"),
                                       item.get("series_title"))) or None
    live_flag = to_bool(first_present(item.get("is_live"), item.get("isLive")))
    if not live_flag and raw_type == "live_event":
        live_flag = True

    return {
        "platform":              PLATFORM,
        "rail":                  rail,
        "page":                  page,
        "section":               section,
        "content_id":            str(cid),
        "series_id":             as_text(first_present(item.get("show_id"), item.get("series_id"))),
        "title":                 title,
        "series_title":          as_text(first_present(item.get("show_title"),
                                                        item.get("series_title"),
                                                        item.get("originalTitle"))),
        "episode_title":         as_text(item.get("episode_title")),
        "content_type":          ctype,
        "content_subtype":       as_text(first_present(item.get("subtype"), item.get("sport_type"),
                                                        item.get("assetSubType"))),
        "is_live":               bool(live_flag),
        "description":           as_text(first_present(item.get("description"), item.get("synopsis"))),
        "year":                  first_present(item.get("release_year"), item.get("year")),
        "release_date":          first_present(item.get("release_date"), item.get("broadcast_date")),
        "rating":                first_present(item.get("age_rating"), item.get("ageRating"),
                                                item.get("certification")),
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
                                     item.get("start_time"), item.get("startTime"),
                                     item.get("broadcast_time"), item.get("broadcastTime"),
                                     item.get("schedule_time"), item.get("scheduleTime"),
                                     item.get("eventStartDate"), item.get("air_date"))),
        "teams":                 teams_text(first_present(
                                     item.get("teams"), item.get("match_title"),
                                     item.get("contestants"))),
        "primary_genre":         genres[0] if genres else None,
        "genre_tags":            ", ".join(genres),
        "category":              category,
        "subcategory":           subcategory,
        "tags":                  ", ".join(tags),
        "languages":             ", ".join(langs),
        "original_language":     original_lang,
        "available_languages":   "; ".join(langs),
        "language_count":        len(langs) or None,
        "is_free":               is_free,
        "subscription_required": sub_req,
        "pay_per_view":          ppv,
        "found_in":              f"{page} > {rail or '(no rail)'}",
        "detail_url":            absolute_url(first_present(
                                     item.get("permalink"), item.get("web_url"),
                                     item.get("url")), BASE),
        "poster_url":            poster,
        "extra_json":            (json.dumps(all_text_fields(item), ensure_ascii=False)
                                  if item else None),
    }


# ── response parser ──────────────────────────────────────────────────────────

class ZEE5Parser(BaseParser):
    def parse(self, url: str, data):
        if not is_content_url(url):
            return
        page = self.page_for(url)

        if isinstance(data, list):
            self._items(data, None, page, None)
            return
        if not isinstance(data, dict):
            return

        rails = safe_get(data, "data", "collection", "rails")
        if isinstance(rails, list) and rails:
            for r in rails:
                if not isinstance(r, dict):
                    continue
                rail = as_text(first_present(r.get("title"), r.get("originalTitle"))) or None
                section = first_present(r.get("id"))
                items = first_present(r.get("contents"), r.get("items")) or []
                self._items(items, rail, page,
                            str(section) if section is not None else None)
            return

        progs = safe_get(data, "data", "programGuide")
        if isinstance(progs, list) and progs:
            for p in progs:
                if not isinstance(p, dict):
                    continue
                rail = as_text(first_present(p.get("title"), p.get("originalTitle"))) or None
                section = first_present(p.get("id"))
                items = p.get("contents") or []
                self._items(items, rail, page,
                            str(section) if section is not None else None)
            return

        buckets = first_present(data.get("bucket_response"),
                                safe_get(data, "data", "buckets"))
        if isinstance(buckets, dict):
            buckets = [buckets]
        if isinstance(buckets, list) and buckets:
            for b in buckets:
                if not isinstance(b, dict):
                    continue
                rail = as_text(first_present(b.get("bucket_name"), b.get("name"))) or None
                section = first_present(b.get("bucket_id"), b.get("id"))
                items = first_present(b.get("items"), b.get("assets"),
                                      b.get("contents")) or []
                self._items(items, rail, page,
                            str(section) if section is not None else None)
                self.maybe_slug(first_present(b.get("view_all_url"), b.get("link")))
            return

        if "id" in data and "title" in data:
            self.add(_row(data, None, page, None))
            return

        items = first_present(data.get("response"), data.get("result"),
                              safe_get(data, "data", "items"), data.get("items"))
        if isinstance(items, list):
            self._items(items, None, page, None)

    def _items(self, items, rail, page, section):
        if not isinstance(items, list):
            return
        for it in items:
            self.add(_row(it, rail, page, section))


# ── crawl-time policy: prune non-sports rows from non-sports pages ──────────

def _prune_non_sports(parser: BaseParser) -> int:
    before = len(parser.rows)
    parser.rows = [r for r in parser.rows
                   if r.get("sport") or _is_sports_page(r.get("page"))]
    parser.seen = {(r["page"], r["rail"], r["content_id"]) for r in parser.rows}
    return before - len(parser.rows)


# ── crawler / re-parser ──────────────────────────────────────────────────────

def crawl(seeds: list[str] | None = None, out: str = "zee5_sports.csv",
          raw_path: str = "zee5_raw.jsonl", append: bool = True, delay: float = 1.5,
          headed: bool = True, headless_new: bool = True, debug: bool = False,
          max_pages: int = 40) -> pd.DataFrame:
    parser = ZEE5Parser()
    browser = Browser(parser.parse, raw_path=raw_path, append=append,
                      delay=delay, headed=headed, debug=debug,
                      headless_new=headless_new, raw_filter=is_zee5_host)
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
                    print("  ✗ ZEE5 is rejecting this browser (HTTP 403). Stopping early.")
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
    dropped = _prune_non_sports(parser)
    if dropped:
        print(f"  (dropped {dropped} non-sports rows from non-sports pages)")
    return save(parser.rows, out, COMMON_COLUMNS, platform=PLATFORM)


def parse_file(raw_path: str, out: str = "zee5_sports.csv") -> pd.DataFrame:
    parser = ZEE5Parser()
    reparse(parser, raw_path)
    dropped = _prune_non_sports(parser)
    if dropped:
        print(f"  (dropped {dropped} non-sports rows from non-sports pages)")
    return save(parser.rows, out, COMMON_COLUMNS, platform=PLATFORM)


# ── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--urls", nargs="*", help="extra slug(s) to crawl")
    ap.add_argument("--raw", help="re-parse existing JSONL (no browser)")
    ap.add_argument("--save-raw", default="zee5_raw.jsonl")
    ap.add_argument("--out", default="zee5_sports.csv")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--delay", type=float, default=1.5)
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--headed", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--max-pages", type=int, default=40)
    a = ap.parse_args()

    if a.raw:
        parse_file(a.raw, a.out)
    else:
        crawl(seeds=(a.urls or []) + SPORTS_SEEDS, out=a.out, raw_path=a.save_raw,
              append=not a.overwrite, delay=a.delay, headed=not a.headless,
              headless_new=True, debug=a.debug, max_pages=a.max_pages)
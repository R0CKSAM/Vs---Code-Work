"""
sonyliv_catalog.py — scrape the SonyLIV sports catalog.  (AUDITED + REAL-SHAPE v3)

Verified against a live capture (apiv3.sonyliv.com):
  PAGE-V2/2245           resultObj.containers[]  — rail descriptors or promo cards
  TRAY/EXTCOLLECTION/*   resultObj.containers[]  — content items (metadata carries the asset)
  TRAY/SEARCH/VOD        same as EXTCOLLECTION
  DETAIL-V2/<id>         resultObj.trays.containers[]

Access / languages / sub-genre live under metadata.emfAttributes.

Rows on non-sports browsed pages that have no detected sport are pruned once,
after the crawl, by crawl() — not by _row(). _row() stays a pure row-builder.
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

PLATFORM = "SonyLIV"
BASE = "https://www.sonyliv.com"
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

# Real subtypes observed in the capture. `Launcher` is UI chrome — dropped.
_CTYPE = {
    "EPISODE": "Episode", "SHOW": "Show", "SERIES": "Show", "MOVIE": "Movie",
    "CLIP": "Clip", "SPORTS_CLIP": "Clip", "SPORTS_CLIPS": "Clip",
    "HIGHLIGHT": "Clip", "HIGHLIGHTS": "Clip",
    "TRAILER": "Trailer", "PROMO": "Trailer", "PREVIEW": "Trailer", "TEASER": "Trailer",
    "LIVE": "Live", "LIVE_EVENT": "Live",
    "MATCH": "Match", "FULL_MATCH": "Match", "SPORT": "Match", "SPORTS": "Match",
    "EVENT": "Match", "STAGE": "Match", "TOURNAMENT": "Tournament",
    "EPISODIC_SHOW": "Show", "EPISODIC": "Show", "MOVIE_BUNDLE": "Movie",
    "VOD": "Video", "MUSIC_VIDEO": "Clip", "SONG": "Clip",
}
# Subtypes that are UI chrome, not catalogue content.
_NON_CONTENT_SUBTYPES = {"LAUNCHER", "NAVIGATION", "NAV", "MENU", "BANNER"}

_SPORTS_PAGE_RE = re.compile(r"sport|game|match|cricket|football|kabaddi|tennis|"
                             r"hockey|badminton|wrestl|athletic|ufc|golf|chess", re.I)


def _is_sports_page(page: str | None) -> bool:
    return bool(page and _SPORTS_PAGE_RE.search(page))


def is_sonyliv_host(url: str) -> bool:
    h = (urlparse(url).hostname or "").lower()
    return h == "sonyliv.com" or h.endswith(".sonyliv.com")


# ── container → item normaliser ─────────────────────────────────────────────

def _normalise_item(container: dict) -> dict | None:
    if not isinstance(container, dict):
        return None
    md = container.get("metadata")
    am = container.get("assetMetadata")
    if (isinstance(md, dict) and md.get("title")
            and (md.get("contentId") is not None
                 or container.get("layout") == "CONTENT_ITEM")):
        return md
    if (isinstance(am, dict) and am.get("title")
            and (am.get("contentId") or am.get("id"))):
        return am
    return None


# ── row builder (pure — no crawl-time policy) ────────────────────────────────

def _row(asset: dict, rail: str | None, page: str, section: str | None) -> dict | None:
    if not isinstance(asset, dict):
        return None
    cid = first_present(asset.get("contentId"), asset.get("id"), asset.get("assetId"))
    if cid is None:
        return None

    title = as_text(first_present(
        asset.get("title"), asset.get("contentTitle"), asset.get("assetTitle"),
        asset.get("episodeTitle"), asset.get("name"),
        safe_get(asset, "metadata", "label"),
    ))
    if not title:
        return None

    emf = asset.get("emfAttributes")
    if not isinstance(emf, dict):
        emf = {}

    raw_type = as_text(first_present(
        asset.get("contentSubtype"), asset.get("objectSubtype"),
        asset.get("contentType"), asset.get("objectType"),
        asset.get("assetType"),
    )).upper()

    if raw_type in _NON_CONTENT_SUBTYPES:
        return None

    ctype = _CTYPE.get(raw_type, raw_type.title() or "Other")

    genres = as_str_list(first_present(
        asset.get("genres"), asset.get("genre"), asset.get("genreList"),
    ))
    sub_genres = as_str_list(first_present(emf.get("sub_genre"), emf.get("subGenre")))
    sport, sport_src = detect_sport(genres + sub_genres, title, rail, page, section)

    category = None
    cats = asset.get("categories")
    if isinstance(cats, list) and cats and isinstance(cats[0], dict):
        category = as_text(cats[0].get("categoryName")) or None
    if not category:
        category = as_text(first_present(
            asset.get("category"), asset.get("categoryName"),
            asset.get("primaryCategory"), safe_get(asset, "metadata", "category"),
        )) or None
    subcategory = as_text(first_present(
        asset.get("subCategory"), asset.get("sub_category"),
        asset.get("subGenre"), asset.get("genreSubType"),
        sub_genres[0] if sub_genres else None,
    )) or None
    tags = as_str_list(first_present(
        emf.get("snp_tags"),
        asset.get("tags"), asset.get("tagList"),
        asset.get("keywords"), asset.get("contentTags"),
    ))

    is_free, sub_req, ppv = parse_access(
        free_flag=first_present(asset.get("isFreeContent"), asset.get("isFree")),
        mode=first_present(
            emf.get("value"), emf.get("advertising"),
            asset.get("accessType"), asset.get("subscriptionType"),
            asset.get("businessType"),
        ),
        ppv_flag=first_present(asset.get("isPayPerView"), asset.get("isPPV")),
    )

    langs: list[str] = []
    audio_list = emf.get("audio_language_list")
    if isinstance(audio_list, list):
        for al in audio_list:
            if isinstance(al, dict):
                n = as_text(al.get("lang_label") or al.get("lang_code"))
                if n and n not in langs:
                    langs.append(n)
    if not langs:
        langs = as_str_list(first_present(
            asset.get("audioLanguages"), asset.get("languages"),
            emf.get("audio_languages"), asset.get("language"),
        ))
    original_lang = as_text(first_present(
        asset.get("originalLanguage"), asset.get("original_language"),
        emf.get("region_of_origin"),
    )) or None

    poster = first_present(
        emf.get("thumbnail"), emf.get("landscape_thumb"),
        emf.get("portrait_thumb"), emf.get("img_poster_2000_3000"),
        safe_get(asset, "thumbnails", "LANDSCAPE", "url"),
        safe_get(asset, "thumbnails", "PORTRAIT", "url"),
        asset.get("posterImageURL"),
    )
    duration_label = first_present(asset.get("durationLabel"), asset.get("runTime"))
    tournament = as_text(first_present(
        asset.get("tournament"), asset.get("seriesTitle"), asset.get("league"),
    )) or None
    live_flag = to_bool(first_present(asset.get("isLive"), emf.get("isLive")))

    release_date = first_present(
        asset.get("broadcastDate"), asset.get("releaseDate"), emf.get("release_date"),
    )
    if not release_date and asset.get("originalAirDate"):
        release_date = to_utc_iso(asset.get("originalAirDate"))

    return {
        "platform":              PLATFORM,
        "rail":                  rail,
        "page":                  page,
        "section":               section,
        "content_id":            str(cid),
        "series_id":             as_text(first_present(asset.get("seriesId"), asset.get("baseContentId"))),
        "title":                 title,
        "series_title":          as_text(first_present(asset.get("showName"), asset.get("seriesTitle"))),
        "episode_title":         as_text(asset.get("episodeTitle")),
        "content_type":          ctype,
        "content_subtype":       as_text(first_present(
                                     asset.get("contentSubtype"), asset.get("objectSubtype"),
                                     asset.get("subType"), asset.get("sportType"))),
        "is_live":               bool(live_flag) or raw_type in ("LIVE", "LIVE_EVENT"),
        "description":           as_text(first_present(
                                     asset.get("longDescription"), asset.get("shortDescription"),
                                     asset.get("description"), asset.get("assetDescription"))),
        "year":                  first_present(asset.get("releaseYear"), asset.get("year"),
                                               emf.get("release_year")),
        "release_date":          release_date,
        "rating":                first_present(asset.get("certification"), asset.get("rating"),
                                               asset.get("ageRating"), asset.get("pcVodLabel")),
        "duration_sec":          duration_to_sec(asset.get("duration"), duration_label),
        "duration_label":        duration_label,
        "season_number":         first_present(asset.get("seasonNumber"), asset.get("season")),
        "episode_number":        first_present(asset.get("episodeNumber"), asset.get("episode")),
        "episode_count":         first_present(asset.get("episodeCount"), asset.get("totalEpisodes")),
        "sport":                 sport,
        "sport_source":          sport_src,
        "tournament":            tournament,
        "match_status":          first_present(asset.get("matchStatus"), asset.get("liveStatus")),
        "match_start_utc":       to_utc_iso(first_present(
                                     asset.get("startTime"), asset.get("broadcastStartTime"),
                                     asset.get("scheduleTime"), asset.get("eventStartDate"),
                                     asset.get("originalAirDate"))),
        "teams":                 teams_text(first_present(
                                     asset.get("teams"), asset.get("matchTitle"),
                                     asset.get("contestants"))),
        "primary_genre":         genres[0] if genres else None,
        "genre_tags":            ", ".join(genres + [g for g in sub_genres if g not in genres]),
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
                                     asset.get("webURL"), asset.get("uri"), asset.get("slug"),
                                     safe_get(asset, "actions", 0, "uri")
                                     if isinstance(asset.get("actions"), list) else None,
                                 ), BASE),
        "poster_url":            poster,
        "extra_json":            (json.dumps(all_text_fields(asset), ensure_ascii=False)
                                  if asset else None),
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

        for wrapper in (safe_get(data, "resultObj"),
                        data.get("data"),
                        data.get("result")):
            if not isinstance(wrapper, dict):
                continue

            trays = safe_get(wrapper, "trays", "containers")
            if isinstance(trays, list) and trays:
                for tray in trays:
                    self._tray(tray, page, depth=0)
                return

            containers = wrapper.get("containers")
            if isinstance(containers, list) and containers:
                top_rail = as_text(wrapper.get("trayTitle")) or None
                for c in containers:
                    self._tray(c, page, depth=0, default_rail=top_rail)
                return

            items = first_present(wrapper.get("items"), wrapper.get("contents"),
                                  wrapper.get("assets"))
            if isinstance(items, list):
                self._items(items, None, page, None)
                return

            if "id" in wrapper and "title" in wrapper:
                self.add(_row(wrapper, None, page, None))
                return

    def _tray(self, tray, page: str, depth: int, default_rail: str | None = None):
        if not isinstance(tray, dict) or depth > 5:
            return
        rail = as_text(first_present(
            tray.get("title"), safe_get(tray, "metadata", "label"), default_rail,
        )) or None
        section = as_text(first_present(tray.get("uri"), tray.get("traySource"))) or None

        item = _normalise_item(tray)
        if item is not None:
            self.add(_row(item, rail, page, section))

        self.maybe_slug(tray.get("uri"))

        assets_raw = tray.get("assets")
        if isinstance(assets_raw, dict):
            assets = first_present(assets_raw.get("items"), assets_raw.get("contents")) or []
            self._items(assets, rail, page, section)
        elif isinstance(assets_raw, list):
            self._items(assets_raw, rail, page, section)
        items = tray.get("items")
        if isinstance(items, list):
            self._items(items, rail, page, section)

        nested = tray.get("containers")
        if isinstance(nested, list):
            for t in nested:
                self._tray(t, page, depth + 1, default_rail=rail)

    def _items(self, assets, rail, page, section):
        if not isinstance(assets, list):
            return
        for a in assets:
            normalised = _normalise_item(a) if isinstance(a, dict) else None
            self.add(_row(normalised or a, rail, page, section))


# ── crawl-time policy: prune non-sports rows from non-sports pages ──────────

def _prune_non_sports(parser: BaseParser) -> int:
    before = len(parser.rows)
    parser.rows = [r for r in parser.rows
                   if r.get("sport") or _is_sports_page(r.get("page"))]
    # re-sync `seen` so a later add() of the same key doesn't re-add a pruned row
    parser.seen = {(r["page"], r["rail"], r["content_id"]) for r in parser.rows}
    return before - len(parser.rows)


# ── crawler / re-parser ──────────────────────────────────────────────────────

def crawl(seeds: list[str] | None = None, out: str = "sonyliv_sports.csv",
          raw_path: str = "sonyliv_raw.jsonl", append: bool = True, delay: float = 1.5,
          headed: bool = True, headless_new: bool = True, debug: bool = False,
          max_pages: int = 40) -> pd.DataFrame:
    parser = SonyLIVParser()
    browser = Browser(parser.parse, raw_path=raw_path, append=append,
                      delay=delay, headed=headed, debug=debug,
                      headless_new=headless_new, raw_filter=is_sonyliv_host)
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
                    print("  ✗ SonyLIV is rejecting this browser (HTTP 403). Stopping early.")
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


def parse_file(raw_path: str, out: str = "sonyliv_sports.csv") -> pd.DataFrame:
    """Re-parse a raw JSONL. Applies the same crawl-time prune so the CSV matches
    what a live crawl would produce."""
    parser = SonyLIVParser()
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
    ap.add_argument("--save-raw", default="sonyliv_raw.jsonl")
    ap.add_argument("--out", default="sonyliv_sports.csv")
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
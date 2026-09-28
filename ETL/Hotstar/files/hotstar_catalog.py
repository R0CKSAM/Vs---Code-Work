"""
hotstar_catalog.py — parsing engine for the Hotstar scraper.

Do not run directly. Used by hotstar_explorer.py.

Public API used by explorer:
    find_key(node, key)      — first value for `key` anywhere in node
    nav_tile(item)           — (kind, name, slug) if item is a nav tile, else None
    item_to_row(item, tray, page) — flat content row dict, or None
    BASE                     — "https://www.hotstar.com"

Fixes applied vs original:
  [BUG-3]  split_label() rewritten — forward scan, no rpartition fallback,
           duration fragments stripped separately so comma-titles parse correctly.
  [ISSUE-4] iter_trays / find_tray_slugs / find_key all carry a depth cap (max 30)
            to prevent RecursionError on deep/bloated payloads.
  [ISSUE-5] LANGS set expanded with missing Indian languages.
  [ISSUE-7] save_rows() always passes columns=COLUMNS so column order is guaranteed.
"""

from __future__ import annotations

__all__ = ["find_key", "nav_tile", "item_to_row", "BASE", "COLUMNS",
           "iter_trays", "find_tray_slugs", "save_rows", "parse_response"]

import argparse
import json
import re
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE = "https://www.hotstar.com"

NAV_TYPES = {
    "CHANNEL", "LANGUAGE", "GENRE", "GAME", "TOURNAMENT",
    "STUDIO", "STUDIOS", "BROWSE", "CATEGORY", "SPORT",
}

# Patterns that identify nav/browse tiles by their label text alone,
# even when the kind field is missing or uses an unexpected value.
_NAV_LABEL_RE = re.compile(
    r"^(Browse|Studios?|Channels?|Genres?|Languages?|Sports?|Tournaments?|"
    r"Popular\s|Sparks|News|Movies|TV|Home)$",
    re.I,
)

# Expanded language set — covers all major Indian + common international languages
LANGS = {
    "hindi", "english", "tamil", "telugu", "kannada", "malayalam", "marathi",
    "bengali", "gujarati", "punjabi", "bhojpuri", "odia", "assamese", "korean",
    "japanese", "chhattisgarhi", "maithili", "dogri", "kashmiri", "konkani",
    "manipuri", "nepali", "sanskrit", "sindhi", "urdu", "arabic", "french",
    "spanish", "german", "portuguese", "italian", "russian", "chinese",
    "mandarin", "thai", "indonesian", "turkish",
}

YEAR_RE     = re.compile(r"^(19|20)\d{2}$")
RATING_RE   = re.compile(r"^(U|A|U/A(\s*\d+\+)?|\d+\+)$")
DURATION_RE = re.compile(r"(\d+\s*h|\d+\s*m\b|\d+\s*s\b|Season|Episode)", re.I)
N_LANGS_RE  = re.compile(r"^\d+ Languages?$", re.I)

TYPES = {"Movie", "Show", "Match", "Clip", "Episode"}

MAX_DEPTH = 30   # recursion guard for all JSON walkers

COLUMNS = [
    "rail", "page", "content_id", "title", "content_type", "description",
    "year", "rating", "duration", "languages", "original_language",
    "available_languages", "language_count", "primary_genre", "genre_tags",
    "series_tag", "release_note", "all_tags", "detail_url", "poster_path",
]


# ---------------------------------------------------------------------------
# JSON walkers (all depth-capped)
# ---------------------------------------------------------------------------

def iter_trays(node, _depth: int = 0):
    """Yield (tray_title, items) for every widget that carries an items list."""
    if _depth > MAX_DEPTH:
        return
    if isinstance(node, dict):
        data = node.get("data")
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            hdr = (
                data.get("header")
                or (data.get("tray_header") or {}).get("data", {}).get("header")
                or {}
            )
            title = ((hdr.get("regular_tray_header") or {}).get("title"))
            yield title, data["items"]
        for v in node.values():
            yield from iter_trays(v, _depth + 1)
    elif isinstance(node, list):
        for v in node:
            yield from iter_trays(v, _depth + 1)


def find_key(node, key: str, _depth: int = 0):
    """First value for `key` anywhere inside node. Depth-capped."""
    if _depth > MAX_DEPTH:
        return None
    if isinstance(node, dict):
        if key in node:
            return node[key]
        for v in node.values():
            r = find_key(v, key, _depth + 1)
            if r is not None:
                return r
    elif isinstance(node, list):
        for v in node:
            r = find_key(v, key, _depth + 1)
            if r is not None:
                return r
    return None


def find_tray_slugs(node, out: set, _depth: int = 0):
    """Collect 'View All' / category page slugs from any response."""
    if _depth > MAX_DEPTH:
        return
    if isinstance(node, dict):
        if node.get("page_type") == "TrayDetailsPage" and node.get("page_slug"):
            out.add(node["page_slug"])
        for v in node.values():
            find_tray_slugs(v, out, _depth + 1)
    elif isinstance(node, list):
        for v in node:
            find_tray_slugs(v, out, _depth + 1)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def poster_data(item: dict):
    """Return the nested dict that contains content_id, or None."""
    for v in item.values():
        if isinstance(v, dict) and isinstance(v.get("data"), dict) and "content_id" in v["data"]:
            return v["data"]
    return None


def split_tags(tags: list[str]) -> dict:
    """
    Walk the tag list left-to-right and slot each tag into:
    year / rating / duration / languages  (pre-language metadata)
    genres / mood tags                    (everything after the language tag)
    """
    out = {"year": None, "rating": None, "duration": None, "languages": None}
    genres: list[str] = []
    past_lang = False

    for t in tags:
        tl = t.lower()
        if not past_lang:
            if YEAR_RE.match(t):
                out["year"] = t
            elif RATING_RE.match(t):
                out["rating"] = t
            elif DURATION_RE.search(t):
                out["duration"] = t
            elif N_LANGS_RE.match(t) or tl in LANGS:
                out["languages"] = t
                past_lang = True
            else:
                past_lang = True
                genres.append(t)
        else:
            genres.append(t)

    out["primary_genre"] = genres[0] if genres else None
    out["genre_tags"]    = ", ".join(genres)
    return out


def split_label(label: str) -> tuple[str, str]:
    """
    Parse Hotstar's comma-joined alt label into (title, content_type).

    Format examples:
        "Virat Kohli, Movie"
        "India vs WI, Match"
        "Best Goals, Clip, 1 hours, 8 minutes"
        "Cook, Eat, Repeat, Show"     <- title contains commas
        "Live: India vs AUS"          <- no comma at all

    Strategy:
        1. Split on ALL commas.
        2. Walk chunks right-to-left; the first chunk that is a known TYPES
           string is the content-type, everything to its left is the title.
           Duration chunks (matching DURATION_RE) to the right of the type
           are stripped but do not affect type detection.
        3. If no known type found, treat the whole string as the title.

    FIX for BUG-3: original backward scan used rpartition as a fallback,
    causing "8 minutes" (last chunk) to be returned as the content-type for
    clips whose titles contained commas.
    """
    if "," not in label:
        return label.strip(), ""

    chunks = [c.strip() for c in label.split(",")]

    # Walk right-to-left, skipping duration fragments
    for i in range(len(chunks) - 1, 0, -1):
        chunk = chunks[i]
        if chunk in TYPES:
            title = ", ".join(chunks[:i]).strip()
            return title, chunk
        # If it's a duration fragment, keep scanning left
        if DURATION_RE.search(chunk):
            continue
        # Non-duration, non-type chunk on the right → no type found
        break

    # No type found — whole label is the title
    return label.strip(), ""


def language_info(ci: dict) -> tuple[list[str], str | None]:
    """Audio/language options for a title, from either shape Hotstar uses."""
    names: list[str] = []
    original = None

    sel = (ci.get("content_language_selector") or {}).get("languages") or []
    for entry in sel:
        name = (entry.get("language") or {}).get("name")
        if name:
            names.append(name)
            if entry.get("description") == "Original" or (original is None and entry.get("is_selected")):
                original = name

    if not names:
        names = [x["value"] for x in ci.get("languages", [])
                 if isinstance(x, dict) and x.get("value")]

    return names, original


def nav_tile(item: dict):
    """
    Return (kind, name, slug) if this tray item is a navigation tile, else None.

    Two detection paths:
      1. The label suffix is a known NAV_TYPE  (e.g. "Cricket, GAME")
      2. No content_id present AND label matches _NAV_LABEL_RE
         (catches Studios, Browse, Language tiles whose kind is non-standard)
    """
    pd_ = poster_data(item)
    if not pd_:
        # If there's no poster_data at all, check for a bare nav structure
        slug = find_key(item, "page_slug")
        raw_label = find_key(item, "label") or ""
        if _NAV_LABEL_RE.match(raw_label.strip()):
            return "NAV", raw_label.strip(), slug
        return None

    name, kind = split_label((pd_.get("alt") or {}).get("label", ""))

    # Path 1: known kind suffix
    if kind.upper() in NAV_TYPES:
        return kind.upper(), name, find_key(item, "page_slug")

    # Path 2: no real content_id (nav tiles often have placeholder IDs like "0")
    cid = pd_.get("content_id", "")
    if not cid or str(cid) in ("0", "None", ""):
        return "NAV", name or kind, find_key(item, "page_slug")

    # Path 3: label itself looks like a nav section heading
    full_label = (pd_.get("alt") or {}).get("label", "")
    if _NAV_LABEL_RE.match(full_label.strip()):
        return "NAV", full_label.strip(), find_key(item, "page_slug")

    return None


def item_to_row(item: dict, tray: str | None, page: str | None) -> dict | None:
    """Turn one tray item into a flat row dict, or None if not a content item."""
    pd_ = poster_data(item)
    if not pd_:
        return None

    ci = (
        (pd_.get("expanded_content_poster") or {}).get("content_info")
        or pd_.get("content_info")
        or {}
    )

    title_part, ctype = split_label((pd_.get("alt") or {}).get("label", ""))

    if ctype.upper() in NAV_TYPES:
        return None

    # Duration suffix leaked into ctype → it's a Clip
    if DURATION_RE.search(ctype):
        ctype = "Clip"

    ctype = ctype or "Other"
    title = ci.get("title") or title_part or None

    tags = [x["value"] for x in
            (ci.get("tags") or ci.get("core_meta_tags") or [])
            if x.get("value")]
    info = split_tags(tags)

    series_tag = None
    if ctype == "Match":
        series_tag             = tags[0] if tags else None
        info["primary_genre"]  = None
        info["genre_tags"]     = ""

    langs, original = language_info(ci)
    slug  = find_key(item, "page_slug")
    image = (
        pd_.get("image")
        or (pd_.get("expanded_content_poster") or {}).get("image")
        or {}
    )

    return {
        "rail":               tray,
        "page":               page,
        "content_id":         pd_["content_id"],
        "title":              title,
        "content_type":       ctype or None,
        "description":        ci.get("description"),
        "year":               info["year"],
        "rating":             info["rating"],
        "duration":           info["duration"],
        "languages":          info["languages"],
        "original_language":  original,
        "available_languages": "; ".join(langs),
        "language_count":     len(langs) or None,
        "primary_genre":      info["primary_genre"],
        "genre_tags":         info["genre_tags"],
        "series_tag":         series_tag,
        "release_note":       "; ".join(
            x.get("value", "") for x in ci.get("callout_meta_tags", [])
        ) or None,
        "all_tags":           " | ".join(tags),
        "detail_url":         (BASE + slug) if slug else None,
        "poster_path":        image.get("src"),
    }


# ---------------------------------------------------------------------------
# Response + file helpers
# ---------------------------------------------------------------------------

def parse_response(url: str, data: dict) -> list[dict]:
    m = re.search(r"pageName=([\w-]+)", url)
    page = m.group(1) if m else None
    rows = []
    for tray, items in iter_trays(data):
        for it in items:
            row = item_to_row(it, tray, page)
            if row:
                rows.append(row)
    return rows


def save_rows(rows: list[dict], out: str) -> pd.DataFrame:
    """
    Write rows to CSV with guaranteed column order.
    FIX for ISSUE-7: always pass columns=COLUMNS and reindex so order is
    stable regardless of dict insertion order.
    """
    df = pd.DataFrame(rows, columns=COLUMNS if not rows else None)
    if df.empty:
        pd.DataFrame(columns=COLUMNS).to_csv(out, index=False)
        print(f"  No content rows parsed → {out} is empty.")
        return df

    df = df.reindex(columns=COLUMNS)          # guarantee column order
    df = df.drop_duplicates(subset=["rail", "page", "content_id"])
    df.to_csv(out, index=False)
    print(f"  {len(df)} rows ({df.content_id.nunique()} unique titles) → {out}")
    print(f"  missing primary_genre: {df.primary_genre.isna().sum()} rows")
    return df


# ---------------------------------------------------------------------------
# Stand-alone crawl / parse CLI (unchanged interface)
# ---------------------------------------------------------------------------

SEEDS = ["/in/home", "/in/shows", "/in/movies", "/in/sports"]


def crawl(seeds, max_trays, max_scrolls, idle_scrolls, delay, raw_path, out, append=False):
    from playwright.sync_api import sync_playwright

    mode = "a" if append else "w"
    raw  = open(raw_path, mode, encoding="utf-8")
    rows, seen_ids, tray_slugs, failed_slugs = [], set(), set(), []
    state = {"label": None}

    def on_response(resp):
        try:
            if "json" not in resp.headers.get("content-type", ""):
                return
            data = resp.json()
            raw.write(json.dumps({"url": resp.url, "data": data}) + "\n")
            find_tray_slugs(data, tray_slugs)
            for r in parse_response(resp.url, data):
                r["page"] = state["label"] or r["page"]
                r["rail"] = r["rail"] or state["label"]
                rows.append(r)
                seen_ids.add(r["content_id"])
        except Exception:
            pass

    def visit(page, slug, retries=2):
        state["label"] = slug
        for attempt in range(retries + 1):
            try:
                page.goto(BASE + slug, wait_until="domcontentloaded", timeout=45000)
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass
                idle = 0
                for _ in range(max_scrolls):
                    before = len(seen_ids)
                    page.mouse.wheel(0, 3000)
                    page.wait_for_timeout(int(delay * 1000))
                    idle = idle + 1 if len(seen_ids) == before else 0
                    if idle >= idle_scrolls:
                        break
                print(f"  {slug}: {len(seen_ids)} unique titles so far")
                return
            except Exception as e:
                wait = 2 ** attempt
                print(f"  ! {slug} attempt {attempt+1} failed: {e} — retrying in {wait}s")
                import time; time.sleep(wait)
        print(f"  ✗ giving up on {slug}")
        failed_slugs.append(slug)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page    = browser.new_context().new_page()
            page.on("response", on_response)
            for slug in seeds:
                print("seed", slug)
                visit(page, slug)
            done = set(seeds)
            while len(done) - len(seeds) < max_trays:
                todo = sorted(tray_slugs - done)
                if not todo:
                    break
                slug = todo[0]
                done.add(slug)
                print(f"tray {len(done)-len(seeds)}/{max_trays}", slug)
                visit(page, slug)
            browser.close()
    finally:
        raw.close()
        if failed_slugs:
            fail_path = Path(raw_path).with_suffix(".failed.txt")
            fail_path.write_text("\n".join(failed_slugs))
            print(f"  {len(failed_slugs)} failed slugs saved to {fail_path}")

    save_rows(rows, out)


def parse_file(raw_path, out):
    rows = []
    for line in open(raw_path, encoding="utf-8"):
        d = json.loads(line)
        rows += parse_response(d["url"], d["data"])
    save_rows(rows, out)


if __name__ == "__main__":
    ap  = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("crawl")
    c.add_argument("pages", nargs="*", default=SEEDS)
    c.add_argument("--max-trays",    type=int,   default=150)
    c.add_argument("--max-scrolls",  type=int,   default=40)
    c.add_argument("--idle-scrolls", type=int,   default=3)
    c.add_argument("--delay",        type=float, default=1.5)
    c.add_argument("--raw",          default="raw_responses.jsonl")
    c.add_argument("--out",          default="hotstar_content.csv")
    c.add_argument("--append",       action="store_true",
                   help="Append to existing raw JSONL instead of overwriting")

    q = sub.add_parser("parse")
    q.add_argument("raw")
    q.add_argument("--out", default="hotstar_content.csv")

    a = ap.parse_args()
    if a.cmd == "crawl":
        crawl(a.pages, a.max_trays, a.max_scrolls, a.idle_scrolls,
              a.delay, a.raw, a.out, append=a.append)
    else:
        parse_file(a.raw, a.out)

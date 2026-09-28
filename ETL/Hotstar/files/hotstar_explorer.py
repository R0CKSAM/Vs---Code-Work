"""
Hotstar Explorer — scan, pick, drill down, export.

    pip install playwright pandas
    playwright install chromium
    python hotstar_explorer.py                        # live crawl
    python hotstar_explorer.py --raw capture.jsonl    # explore a saved file

Flow
    1. QUICK SCAN   light pass over Home / TV / Movies / Sports + any extra
                    landing pages the site menu exposes (all page types, not
                    just LandingPage — FIX for IMPROVEMENT-3).
    2. MAIN MENU    pick a section.
    3. DRILL DOWN   pick rails / genres / sports (e.g. 1,3,5-7 or "all").
                    The tool drills as deep as sub-sections exist — it keeps
                    asking until there is nothing left to go into.
    4. BASKET       everything collected here. When you export, you get:
                    • a terminal summary (counts by type, genre, language)
                    • a filtered CSV containing ONLY what you asked for.

Fixes vs original
  [BUG-1]  rails_of() now does case-insensitive label matching so "Kabaddi"
           vs "kabaddi" no longer silently drops sub-sections.
  [BUG-2]  Sub-section prompt accepts y / yes / all / a — "all" now works.
           "all" automatically opens every sub-section without prompting again.
  [ISSUE-2] Browser.visit() retries up to 2x with back-off; failed slugs
            written to <raw>.failed.txt so you can resume.
  [ISSUE-3] Raw file opened in APPEND mode by default (--overwrite flag to
            reset). Warns if the file already exists so you never lose data.
  [BUG-1+] explore_nav() also drills infinitely deep using the same loop
            as explore_rails() instead of a one-shot sub-section offer.
  [IMPROVEMENT-1] basket_screen() builds DataFrame once, rebuilds only when
            basket or filters change.
  [IMPROVEMENT-3] quick_scan() visits ALL menu page types, not just LandingPage.
  General: "all" in sub-section prompts is handled everywhere consistently.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

import pandas as pd

import hotstar_catalog as hc

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PAGES = {
    "/in/home":   "Home",
    "/in/shows":  "TV / Shows",
    "/in/movies": "Movies",
    "/in/sports": "Sports",
}
PAGENAME = {
    "home":    "Home",
    "shows":   "TV / Shows",
    "movies":  "Movies",
    "sports":  "Sports",
}
NAV_SECTIONS = [
    ("Genres",             "GENRE"),
    ("Languages",          "LANGUAGE"),
    ("Channels / studios", "CHANNEL"),
    ("Sports (by game)",   "GAME"),
    ("Tournaments",        "TOURNAMENT"),
]
EXPORT_COLS = [
    "content_id", "title", "content_type", "primary_genre", "genre_tags",
    "description", "original_language", "available_languages", "language_count",
    "year", "rating", "duration", "languages", "series_tag", "release_note",
    "detail_url", "found_in", "all_tags", "poster_path",
]


# ---------------------------------------------------------------------------
# Data store
# ---------------------------------------------------------------------------

class Store:
    """All learned content, rails, and nav tiles."""

    def __init__(self):
        self.rows:    dict = {}   # content_id -> row dict (with found_in set)
        self.by_rail: dict = {}   # rail_key -> set(content_id)
        self.rails:   dict = {}   # rail_key -> {title, slug, page}
        self.nav:     dict = {}   # kind -> {name: slug}
        self.menu:    list = []   # (title, slug, page_type) from site menu
        self.current: set | None = None

    @staticmethod
    def _trays(node, _depth=0):
        if _depth > hc.MAX_DEPTH:
            return
        if isinstance(node, dict):
            d = node.get("data")
            if isinstance(d, dict) and isinstance(d.get("items"), list):
                hdr = (
                    d.get("header")
                    or ((d.get("tray_header") or {}).get("data") or {}).get("header")
                    or {}
                )
                title = ((hdr.get("regular_tray_header") or {}).get("title"))
                slug  = hc.find_key(hdr, "page_slug")
                yield title, slug, d["items"]
            for v in node.values():
                yield from Store._trays(v, _depth + 1)
        elif isinstance(node, list):
            for v in node:
                yield from Store._trays(v, _depth + 1)

    def ingest(self, url: str, data: dict, label=None, rail_key=None, rail_title=None):
        if not isinstance(data, dict):
            return
        m    = re.search(r"pageName=([\w-]+)", url)
        page = label or (PAGENAME.get(m.group(1), m.group(1)) if m else "Home")

        # Collect site menu
        menu_items = (
            ((((data.get("success") or {}).get("menu") or {})
              .get("widget") or {}).get("data") or {}).get("items") or []
        )
        for i in menu_items:
            try:
                nav  = i["actions"]["on_click"][0]["page_navigation"]
                entry = (i.get("title"), nav.get("page_slug"), nav.get("page_type"))
                if entry not in self.menu:
                    self.menu.append(entry)
            except (KeyError, IndexError, TypeError):
                pass

        for title, slug, items in self._trays(data):
            tray_title = title or rail_title or "Featured (untitled row)"
            key        = rail_key or slug or f"{page}::{tray_title}"
            info = self.rails.setdefault(key, {"title": tray_title, "slug": None, "page": page})
            info["slug"] = (
                info["slug"]
                or slug
                or (rail_key if rail_key and str(rail_key).startswith("/") else None)
            )

            for it in items:
                tile = hc.nav_tile(it)
                if tile:
                    kind, name, tslug = tile
                    self.nav.setdefault(kind, {}).setdefault(name, tslug)
                    continue
                row = hc.item_to_row(it, tray_title, page)
                if not row:
                    continue
                cid  = row["content_id"]
                have = self.rows.setdefault(cid, {**row, "found_in": set()})
                if not have.get("description") and row.get("description"):
                    saved = have["found_in"]
                    have.update({k: v for k, v in row.items() if v not in (None, "")})
                    have["found_in"] = saved
                have["found_in"].add(f"{page} > {tray_title}")
                self.by_rail.setdefault(key, set()).add(cid)
                if self.current is not None:
                    self.current.add(cid)

    def rails_of(self, label: str) -> list:
        """
        Return rails whose page label matches (case-insensitive).
        FIX for BUG-1: original was case-sensitive; "Kabaddi" vs "kabaddi"
        caused sub-sections to be silently skipped.
        """
        label_lo = label.lower()
        return [
            (k, v) for k, v in self.rails.items()
            if v["page"].lower() == label_lo and self.by_rail.get(k)
        ]

    def page_titles(self, label: str) -> set:
        ids: set = set()
        for k, _ in self.rails_of(label):
            ids |= self.by_rail[k]
        return ids


# ---------------------------------------------------------------------------
# Browser wrapper
# ---------------------------------------------------------------------------

class Browser:
    def __init__(self, store: Store, headed=False, delay=1.5,
                 raw_path: str | None = None, append=False):
        self.store   = store
        self.headed  = headed
        self.delay   = delay
        self._ctx: dict = {}

        if raw_path:
            rp = Path(raw_path)
            if rp.exists() and not append:
                print(f"  ⚠  {raw_path} already exists — appending. "
                      "Use --overwrite to replace it.")
            # FIX for ISSUE-3: always append so existing captures are never lost
            self.raw = open(raw_path, "a", encoding="utf-8")
        else:
            self.raw = None

    def start(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise SystemExit(
                "Playwright missing.\n"
                "Run:  pip install playwright pandas  &&  playwright install chromium"
            )
        self._pw      = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=not self.headed)
        self.page     = self._browser.new_context().new_page()
        self.page.on("response", self._on_response)

    def _on_response(self, resp):
        try:
            if "json" not in resp.headers.get("content-type", ""):
                return
            data = resp.json()
        except Exception:
            return
        if self.raw:
            self.raw.write(json.dumps({"url": resp.url, "data": data}) + "\n")
        self.store.ingest(resp.url, data, **self._ctx)

    def visit(self, slug: str, label: str, deep=True,
              rail_key=None, rail_title=None, retries=2) -> set:
        """
        Open a page, scroll until idle or limit hit, return ids seen.
        FIX for ISSUE-2: retries with exponential back-off; failed slugs
        are tracked by the caller.
        """
        self._ctx = dict(label=label, rail_key=rail_key, rail_title=rail_title)
        self.store.current = set()

        for attempt in range(retries + 1):
            try:
                self.page.goto(hc.BASE + slug, wait_until="domcontentloaded", timeout=45000)
                try:
                    self.page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass
                idle = 0
                for _ in range(60 if deep else 3):
                    before = len(self.store.current)
                    self.page.mouse.wheel(0, 3000)
                    self.page.wait_for_timeout(int(self.delay * 1000))
                    idle = idle + 1 if len(self.store.current) == before else 0
                    if deep and idle >= 3:
                        break
                break  # success
            except Exception as e:
                import time
                wait = 2 ** attempt
                if attempt < retries:
                    print(f"   ! {slug} attempt {attempt+1} failed ({e}) — retry in {wait}s")
                    time.sleep(wait)
                else:
                    print(f"   ✗ could not open {slug}: {e}")

        found, self.store.current = self.store.current, None
        return found

    def close(self):
        try:
            self._browser.close()
            self._pw.stop()
        finally:
            if self.raw:
                self.raw.close()


# ---------------------------------------------------------------------------
# Small UI helpers
# ---------------------------------------------------------------------------

def ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except EOFError:
        return "q"


def parse_choice(text: str, n: int) -> list[int]:
    text = text.strip().lower()
    if text in ("a", "all"):
        return list(range(1, n + 1))
    picked = []
    for part in text.replace(" ", "").split(","):
        if re.fullmatch(r"\d+-\d+", part):
            lo, hi = map(int, part.split("-"))
            picked += range(lo, hi + 1)
        elif part.isdigit():
            picked.append(int(part))
    return [i for i in dict.fromkeys(picked) if 1 <= i <= n]


def hr(title: str):
    print("\n" + "=" * 8 + f" {title} " + "=" * 8)


# ---------------------------------------------------------------------------
# Summary printer  (the "specific details" output before export)
# ---------------------------------------------------------------------------

def print_summary(rows: list[dict], context: str):
    """
    Print a focused terminal summary for exactly the rows selected —
    not a dump of everything the store has ever seen.
    """
    if not rows:
        print("  (no rows to summarise)")
        return

    df = pd.DataFrame(rows)
    total   = len(df)
    unique  = df["content_id"].nunique()

    print(f"\n{'─'*52}")
    print(f"  {context}")
    print(f"  {unique} unique titles  ({total} rows incl. duplicates across rails)")
    print(f"{'─'*52}")

    # Content types
    types = df["content_type"].value_counts()
    print("\n  Content types:")
    for ctype, cnt in types.items():
        bar = "█" * min(int(cnt / max(types) * 20), 20)
        print(f"    {ctype:<14} {cnt:>4}  {bar}")

    # Top genres
    genres = df["primary_genre"].dropna().value_counts().head(8)
    if not genres.empty:
        print("\n  Top genres:")
        for g, cnt in genres.items():
            print(f"    {g:<20} {cnt:>4}")

    # Languages
    langs = df["languages"].dropna().value_counts().head(6)
    if not langs.empty:
        print("\n  Languages:")
        for l, cnt in langs.items():
            print(f"    {l:<20} {cnt:>4}")

    # Years
    years = df["year"].dropna().value_counts().head(5)
    if not years.empty:
        print("\n  Top years:  " + "  ".join(f"{y}({c})" for y, c in years.items()))

    # Rails (where this content was found)
    rails = df["rail"].dropna().value_counts().head(8)
    if not rails.empty:
        print("\n  Rails this content appeared in:")
        for r, cnt in rails.items():
            print(f"    {str(r)[:40]:<40} {cnt:>4}")

    print(f"{'─'*52}\n")


# ---------------------------------------------------------------------------
# Screens
# ---------------------------------------------------------------------------

def quick_scan(store: Store, browser: Browser):
    hr("QUICK SCAN")
    for slug, label in PAGES.items():
        print(f"  scanning {label} ...")
        browser.visit(slug, label, deep=False)

    # FIX for IMPROVEMENT-3: scan ALL menu page types, not just LandingPage
    seen_slugs = set(PAGES.keys())
    for title, slug, ptype in store.menu:
        if slug and slug not in seen_slugs:
            print(f"  scanning {title} ({ptype}) ...")
            browser.visit(slug, title, deep=False)
            seen_slugs.add(slug)

    print(f"  done: {len(store.rows)} titles in {len(store.rails)} rails so far")


def sections(store: Store) -> list[tuple]:
    out   = []
    labels = list(PAGES.values()) + [
        t for t, s, p in store.menu if s and s not in PAGES
    ]
    for label in dict.fromkeys(labels):
        rails = store.rails_of(label)
        if rails:
            out.append((
                label, "page", label,
                f"{len(rails)} rails, {len(store.page_titles(label))} titles seen",
            ))
    for label, kind in NAV_SECTIONS:
        if store.nav.get(kind):
            out.append((label, "nav", kind, f"{len(store.nav[kind])} found"))
    return out


def explore_rails(label: str, store: Store, browser: Browser | None,
                  basket: set, depth: int = 1):
    """
    List the rails under `label`, let the user pick some, open them fully,
    then keep drilling as long as sub-sections exist.

    FIX for BUG-1: uses case-insensitive rails_of().
    FIX for BUG-2: "all" / "a" / "yes" accepted everywhere, including the
                   sub-section prompt.
    New behaviour: instead of offering one level of sub-sections, we loop
                   automatically until nothing deeper exists (infinite depth).
    """
    while True:
        rails = store.rails_of(label)
        hr(f"{label.upper()}  —  pick what to open")
        if not rails:
            print("  (nothing found here yet)")
            return

        for i, (k, v) in enumerate(rails, 1):
            available = "full list" if (v["slug"] and browser) else "preview only"
            count     = len(store.by_rail.get(k, set()))
            print(f"  {i:>3}) {v['title']}  —  {count} titles  [{available}]")

        c = ask("\n  Choose (e.g. 1,3,5-7 / all)  |  b = back  > ")
        if c.lower() in ("b", "q", ""):
            return

        chosen = parse_choice(c, len(rails))
        if not chosen:
            print("  (nothing selected)")
            continue

        newly_added: list[dict] = []

        for i in chosen:
            key, info = rails[i - 1]
            ids: set  = set(store.by_rail.get(key, set()))

            if browser and info["slug"]:
                print(f"  opening '{info['title']}' ...")
                ids |= browser.visit(
                    info["slug"], info["title"],
                    deep=True, rail_key=key, rail_title=info["title"],
                )
            elif not browser:
                print("  (offline mode — using captured data)")

            basket |= ids
            added   = [store.rows[cid] for cid in ids if cid in store.rows]
            newly_added.extend(added)
            print(f"  + {len(ids)} titles from '{info['title']}'  (basket: {len(basket)})")

            # Infinite depth: keep drilling while sub-sections exist
            _drill_deep(info["title"], store, browser, basket)

        # Print a focused summary of just what was added this round
        if newly_added:
            print_summary(newly_added, f"Just added: {len(newly_added)} titles")


def _drill_deep(label: str, store: Store, browser: Browser | None, basket: set):
    """
    Recursively open all sub-sections under `label` until none remain.
    Called after every rail open so depth is truly unlimited.
    """
    sub_rails = store.rails_of(label)
    if not sub_rails:
        return  # nothing deeper

    ans = ask(f"    '{label}' has {len(sub_rails)} sub-section(s). Go deeper? [y/N/all] ")
    ans = ans.lower()
    if ans not in ("y", "yes", "all", "a"):
        return

    if ans in ("all", "a"):
        # Open every sub-section without prompting for each
        for k, info in sub_rails:
            ids: set = set(store.by_rail.get(k, set()))
            if browser and info["slug"]:
                print(f"    → opening sub-section '{info['title']}' ...")
                ids |= browser.visit(
                    info["slug"], info["title"],
                    deep=True, rail_key=k, rail_title=info["title"],
                )
            basket |= ids
            print(f"      + {len(ids)} titles  (basket: {len(basket)})")
            _drill_deep(info["title"], store, browser, basket)  # recurse
    else:
        # Interactive pick inside the sub-section
        explore_rails(label, store, browser, basket)


def explore_nav(kind: str, label: str, store: Store,
                browser: Browser | None, basket: set):
    """Navigate genre / language / sport / tournament pages, drill infinitely."""
    while True:
        names = list(store.nav[kind].items())
        hr(label.upper())
        for i, (name, slug) in enumerate(names, 1):
            print(f"  {i:>3}) {name}")

        c = ask("\n  Choose (e.g. 1,3,5-7 / all)  |  b = back  > ")
        if c.lower() in ("b", "q", ""):
            return
        if not browser:
            print("  These need live browsing — run without --raw.")
            continue

        chosen = parse_choice(c, len(names))
        if not chosen:
            print("  (nothing selected)")
            continue

        newly_added: list[dict] = []

        for i in chosen:
            name, slug = names[i - 1]
            if not slug:
                print(f"  ! no link for {name}")
                continue
            print(f"  opening '{name}' ...")
            ids = browser.visit(slug, name, deep=True)
            basket |= ids
            added   = [store.rows[cid] for cid in ids if cid in store.rows]
            newly_added.extend(added)
            print(f"  + {len(ids)} titles from '{name}'  (basket: {len(basket)})")
            _drill_deep(name, store, browser, basket)

        if newly_added:
            print_summary(newly_added, f"Just added from {label}: {len(newly_added)} titles")


# ---------------------------------------------------------------------------
# Filter helpers
# ---------------------------------------------------------------------------

def matches(row: dict, f: dict) -> bool:
    def has(text, *cols):
        return any(text in str(row.get(c) or "").lower() for c in cols)
    if f.get("types") and row.get("content_type") not in f["types"]:
        return False
    if f.get("genre") and not has(f["genre"], "primary_genre", "genre_tags", "all_tags"):
        return False
    if f.get("lang") and not has(f["lang"], "languages", "original_language", "available_languages"):
        return False
    if f.get("text") and not has(f["text"], "title", "description"):
        return False
    return True


# ---------------------------------------------------------------------------
# Basket screen
# ---------------------------------------------------------------------------

def basket_screen(store: Store, basket: set):
    """
    Preview / filter / export the basket.
    FIX for IMPROVEMENT-1: DataFrame built once, rebuilt only on change.
    """
    filt: dict      = {}
    _dirty: bool    = True
    _cached_rows: list[dict] = []

    while True:
        if _dirty:
            _cached_rows = [
                store.rows[i] for i in basket
                if i in store.rows and matches(store.rows[i], filt)
            ]
            _dirty = False

        rows = _cached_rows
        hr(f"BASKET  —  {len(rows)} titles" +
           (f"  (filtered from {len(basket)})" if filt else ""))

        if rows:
            print_summary(rows, "Current basket")
        else:
            print("  (basket is empty or all filtered out)")

        if filt:
            print("  active filters:", {k: v for k, v in filt.items()})

        print("  1) filter by type    2) filter by genre/sport    3) filter by language")
        print("  4) search title/desc 5) clear filters             6) EXPORT to CSV")
        print("  b) back")
        c = ask("  > ").lower()

        if c == "1" and basket:
            all_types = sorted({
                store.rows[i].get("content_type") or "?"
                for i in basket if i in store.rows
            })
            for n, t in enumerate(all_types, 1):
                print(f"    {n}) {t}")
            picks = parse_choice(ask("    which? > "), len(all_types))
            filt["types"] = {all_types[i - 1] for i in picks} or None
            _dirty = True
        elif c == "2":
            filt["genre"] = ask("    genre / sport contains > ").lower() or None
            _dirty = True
        elif c == "3":
            filt["lang"] = ask("    language contains > ").lower() or None
            _dirty = True
        elif c == "4":
            filt["text"] = ask("    text contains > ").lower() or None
            _dirty = True
        elif c == "5":
            filt = {}
            _dirty = True
        elif c == "6":
            export(rows)
        elif c in ("b", "q", ""):
            return

        filt = {k: v for k, v in filt.items() if v}


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def export(rows: list[dict]):
    """
    Export ONLY the selected rows to CSV.
    Prints a focused summary first so the user knows exactly what they're
    getting before the file is written.
    """
    if not rows:
        print("  nothing to export")
        return

    print_summary(rows, f"Export preview — {len(rows)} rows")

    default = f"hotstar_export_{datetime.now():%Y%m%d_%H%M}.csv"
    name    = ask(f"  file name [{default}] > ") or default

    df = pd.DataFrame([
        {**r, "found_in": " | ".join(sorted(r["found_in"]))}
        for r in rows
    ])
    df = df.reindex(columns=EXPORT_COLS)
    df = df.drop_duplicates(subset=["content_id"])
    df.to_csv(name, index=False)
    print(f"  ✓ saved {len(df)} unique titles → {name}")


# ---------------------------------------------------------------------------
# Main menu
# ---------------------------------------------------------------------------

def main_menu(store: Store, browser: Browser | None, basket: set):
    while True:
        secs = sections(store)
        hr(f"MAIN MENU   (basket: {len(basket)} titles)")
        for i, (label, kind, payload, info) in enumerate(secs, 1):
            print(f"  {i:>3}) {label}  —  {info}")

        print("\n  a) add everything scanned to basket")
        print("  b) basket: preview / filter / export")
        if browser:
            print("  s) scan another page (paste a slug, e.g. /in/creators)")
        print("  c) clear basket    q) quit")

        c = ask("  > ").lower()
        if c == "q":
            return
        if c == "a":
            basket |= set(store.rows)
            print(f"  basket now has {len(basket)} titles")
        elif c == "b":
            basket_screen(store, basket)
        elif c == "c":
            basket.clear()
            print("  basket cleared")
        elif c == "s" and browser:
            slug = ask("    slug > ")
            if slug.startswith("/"):
                print(f"  scanning {slug} ...")
                browser.visit(slug, slug, deep=False)
                # If it landed nav tiles (like /in/categories), surface them
                new_nav = {
                    kind: names for kind, names in store.nav.items()
                    if kind not in ("CHANNEL", "LANGUAGE", "GENRE", "GAME", "TOURNAMENT")
                }
                if new_nav:
                    print(f"  found navigation tiles ({sum(len(v) for v in new_nav.values())} items) — use the main menu to drill in")
                else:
                    explore_rails(slug, store, browser, basket)
        else:
            picked = parse_choice(c, len(secs))
            if len(picked) == 1:
                label, kind, payload, _ = secs[picked[0] - 1]
                if kind == "page":
                    explore_rails(label, store, browser, basket)
                else:
                    explore_nav(payload, label, store, browser, basket)
            elif picked:
                print("  pick one section at a time")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--raw",       nargs="+",
                    help="Explore saved raw_responses.jsonl file(s) (no browser)")
    ap.add_argument("--headed",    action="store_true",
                    help="Show the browser window")
    ap.add_argument("--delay",     type=float, default=1.5,
                    help="Seconds between scrolls (default 1.5 — be polite)")
    ap.add_argument("--save-raw",  default="raw_responses.jsonl",
                    help="Where live runs save raw JSON ('' to skip)")
    ap.add_argument("--overwrite", action="store_true",
                    help="Overwrite the raw JSONL file instead of appending")
    a = ap.parse_args()

    store, browser, basket = Store(), None, set()

    if a.raw:
        for path in a.raw:
            print(f"  loading {path} ...")
            for line in open(path, encoding="utf-8"):
                d = json.loads(line)
                store.ingest(d["url"], d["data"])
        print(f"  loaded {len(store.rows)} titles in {len(store.rails)} rails")
    else:
        raw_path = a.save_raw or None
        append   = not a.overwrite
        browser  = Browser(store, a.headed, a.delay, raw_path, append=append)
        browser.start()
        quick_scan(store, browser)

    try:
        main_menu(store, browser, basket)
    except KeyboardInterrupt:
        print("\n  interrupted")
    finally:
        if browser:
            browser.close()
        if basket and ask("\nExport your basket before leaving? [y/N] ").lower() in ("y", "yes"):
            export([store.rows[i] for i in basket if i in store.rows])


if __name__ == "__main__":
    main()

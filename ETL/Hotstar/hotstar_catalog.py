"""
Extract title / content type / genre / rail from the JSON the Hotstar web app loads.

Deep crawl (home, TV, movies, sports + every "View All" / category page found):
    pip install playwright pandas
    playwright install chromium
    python hotstar_catalog.py crawl --max-trays 200
    python hotstar_catalog.py crawl /in/movies /in/shows      # only specific pages

Re-parse an existing raw_responses.jsonl (no browser needed):
    python hotstar_catalog.py parse raw_responses.jsonl

Output columns:
    rail         - the tray/row the title appeared in (e.g. "New on JioHotstar"); None = hero banner
    page         - pageName from the request (home, movies, ...)
    content_id, title, content_type (Movie / Show / Match / Clip)
    year, rating, duration, languages
    primary_genre - first genre tag (Hotstar lists genres first, then mood/theme tags)
    genre_tags    - everything after the language tag (genres + mood/theme descriptors)
"""
import argparse
import json
import re

import pandas as pd

NAV_TYPES = {"CHANNEL", "LANGUAGE", "GENRE"}  # navigation tiles, not content
LANGS = {
    "hindi", "english", "tamil", "telugu", "kannada", "malayalam", "marathi", "bengali",
    "gujarati", "punjabi", "bhojpuri", "odia", "assamese", "korean", "japanese",
}
YEAR = re.compile(r"^(19|20)\d{2}$")
RATING = re.compile(r"^(U|A|U/A(\s*\d+\+)?|\d+\+)$")
DURATION = re.compile(r"(\d+\s*h|\d+\s*m\b|Season|Episode)", re.I)
N_LANGS = re.compile(r"^\d+ Languages?$", re.I)


def iter_trays(n):
    """Yield (tray_title, items) for every widget that carries an items list."""
    if isinstance(n, dict):
        data = n.get("data")
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            hdr = data.get("header") or data.get("tray_header", {}).get("data", {}).get("header") or {}
            yield (hdr.get("regular_tray_header") or {}).get("title"), data["items"]
        for v in n.values():
            yield from iter_trays(v)
    elif isinstance(n, list):
        for v in n:
            yield from iter_trays(v)


def poster_data(item):
    for v in item.values():
        if isinstance(v, dict) and isinstance(v.get("data"), dict) and "content_id" in v["data"]:
            return v["data"]
    return None


def split_tags(tags):
    out = {"year": None, "rating": None, "duration": None, "languages": None}
    genres, past_lang = [], False
    for t in tags:
        if not past_lang:
            if YEAR.match(t):
                out["year"] = t
            elif RATING.match(t):
                out["rating"] = t
            elif DURATION.search(t):
                out["duration"] = t
            elif N_LANGS.match(t) or t.lower() in LANGS:
                out["languages"], past_lang = t, True
            else:
                past_lang = True
                genres.append(t)
        else:
            genres.append(t)
    out["primary_genre"] = genres[0] if genres else None
    out["genre_tags"] = ", ".join(genres)
    return out


TYPES = ("Movie", "Show", "Match", "Clip", "Episode")


def split_label(label):
    """'Title,Movie' / 'Title, Clip, 1 hours, 8 minutes' -> (title, content_type)."""
    for i in range(len(label) - 1, -1, -1):
        if label[i] == ",":
            rest = label[i + 1:].strip()
            if rest in TYPES:
                return label[:i].strip(), rest
    title, _, ctype = label.rpartition(",")
    return title.strip(), ctype.strip()


def find_key(n, key):
    """First value for `key` anywhere inside n."""
    if isinstance(n, dict):
        if key in n:
            return n[key]
        for v in n.values():
            r = find_key(v, key)
            if r is not None:
                return r
    elif isinstance(n, list):
        for v in n:
            r = find_key(v, key)
            if r is not None:
                return r
    return None


def language_info(ci):
    """Audio/language options for a title, from either shape Hotstar uses."""
    names, original = [], None
    sel = (ci.get("content_language_selector") or {}).get("languages") or []
    for entry in sel:
        name = (entry.get("language") or {}).get("name")
        if name:
            names.append(name)
            if entry.get("description") == "Original" or (original is None and entry.get("is_selected")):
                original = name
    if not names:  # clips use a flat [{"key": "hin", "value": "Hindi"}] list
        names = [x["value"] for x in ci.get("languages", []) if isinstance(x, dict) and x.get("value")]
    return names, original


def parse_response(url, data):
    m = re.search(r"pageName=([\w-]+)", url)
    page = m.group(1) if m else None
    rows = []
    for tray, items in iter_trays(data):
        for it in items:
            pd_ = poster_data(it)
            if not pd_:
                continue
            ci = (pd_.get("expanded_content_poster") or {}).get("content_info") or pd_.get("content_info") or {}
            title_part, ctype = split_label((pd_.get("alt") or {}).get("label", ""))
            if ctype.upper() in NAV_TYPES:
                continue
            if re.search(r"\d+\s*(minutes?|hours?|seconds?)$", ctype):
                ctype = "Clip"
            title = ci.get("title") or title_part or None
            tags = [x["value"] for x in (ci.get("tags") or ci.get("core_meta_tags") or []) if x.get("value")]
            info = split_tags(tags)
            series_tag = None
            if ctype == "Match":  # sports tags are series/tournament names, not genres
                series_tag, info["primary_genre"], info["genre_tags"] = (tags[0] if tags else None), None, ""
            langs, original = language_info(ci)
            slug = find_key(it, "page_slug")
            image = pd_.get("image") or (pd_.get("expanded_content_poster") or {}).get("image") or {}
            rows.append({
                "rail": tray, "page": page, "content_id": pd_["content_id"],
                "title": title, "content_type": ctype or None,
                "description": ci.get("description"),
                **{k: info[k] for k in ("year", "rating", "duration", "languages")},
                "original_language": original,
                "available_languages": "; ".join(langs),
                "language_count": len(langs) or None,
                "primary_genre": info["primary_genre"], "genre_tags": info["genre_tags"],
                "series_tag": series_tag,
                "release_note": "; ".join(x.get("value", "") for x in ci.get("callout_meta_tags", [])) or None,
                "all_tags": " | ".join(tags),
                "detail_url": (BASE + slug) if slug else None,
                "poster_path": image.get("src"),
            })
    return rows


COLUMNS = ["rail", "page", "content_id", "title", "content_type", "description", "year", "rating",
           "duration", "languages", "original_language", "available_languages", "language_count",
           "primary_genre", "genre_tags", "series_tag", "release_note", "all_tags", "detail_url", "poster_path"]


def save_rows(rows, out):
    """Write rows to CSV; never crash on an empty result (e.g. a detail page with no tray items)."""
    df = pd.DataFrame(rows, columns=COLUMNS if not rows else None)
    if df.empty:
        df.to_csv(out, index=False)
        print(f"No content rows parsed -> {out} is empty. Check the raw JSONL file for the page's data.")
        return df
    df = df.drop_duplicates(subset=["rail", "page", "content_id"])
    df.to_csv(out, index=False)
    print(f"{len(df)} rows ({df.content_id.nunique()} unique titles) -> {out}")
    print(f"  missing primary_genre: {df.primary_genre.isna().sum()} rows")
    return df


BASE = "https://www.hotstar.com"
SEEDS = ["/in/home", "/in/shows", "/in/movies", "/in/sports"]


def find_tray_slugs(n, out):
    """Collect 'View All' / category page slugs from any response."""
    if isinstance(n, dict):
        if n.get("page_type") == "TrayDetailsPage" and n.get("page_slug"):
            out.add(n["page_slug"])
        for v in n.values():
            find_tray_slugs(v, out)
    elif isinstance(n, list):
        for v in n:
            find_tray_slugs(v, out)


def crawl(seeds, max_trays, max_scrolls, idle_scrolls, delay, raw_path, out):
    from playwright.sync_api import sync_playwright
    raw = open(raw_path, "w", encoding="utf-8")
    rows, seen_ids, tray_slugs, state = [], set(), set(), {"label": None}

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

    def visit(page, slug):
        state["label"] = slug
        try:
            page.goto(BASE + slug, wait_until="domcontentloaded", timeout=45000)
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
        except Exception as e:
            print(f"  ! could not open {slug}: {e}")
            return
        idle = 0
        for _ in range(max_scrolls):          # scroll until nothing new shows up
            before = len(seen_ids)
            page.mouse.wheel(0, 3000)
            page.wait_for_timeout(int(delay * 1000))
            idle = idle + 1 if len(seen_ids) == before else 0
            if idle >= idle_scrolls:
                break
        print(f"  {slug}: {len(seen_ids)} unique titles so far")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_context().new_page()
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
                print(f"tray {len(done) - len(seeds)}/{max_trays}", slug)
                visit(page, slug)
            browser.close()
    finally:
        raw.close()  # raw_responses is kept even if the crawl is interrupted

    save_rows(rows, out)


def parse_file(raw_path, out):
    rows = []
    for line in open(raw_path, encoding="utf-8"):
        d = json.loads(line)
        rows += parse_response(d["url"], d["data"])
    save_rows(rows, out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("crawl")
    c.add_argument("pages", nargs="*", default=SEEDS, help="page slugs, default: home/shows/movies/sports")
    c.add_argument("--max-trays", type=int, default=150, help="max View All / category pages to open")
    c.add_argument("--max-scrolls", type=int, default=40)
    c.add_argument("--idle-scrolls", type=int, default=3, help="stop after N scrolls with no new titles")
    c.add_argument("--delay", type=float, default=1.5, help="seconds between scrolls (be polite)")
    c.add_argument("--raw", default="raw_responses.jsonl")
    c.add_argument("--out", default="hotstar_content.csv")
    q = sub.add_parser("parse")
    q.add_argument("raw")
    q.add_argument("--out", default="hotstar_content.csv")
    a = ap.parse_args()
    if a.cmd == "crawl":
        crawl(a.pages, a.max_trays, a.max_scrolls, a.idle_scrolls, a.delay, a.raw, a.out)
    else:
        parse_file(a.raw, a.out)

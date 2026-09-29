"""
catalog_base.py — shared types, helpers and output logic for all OTT scrapers.

Used by:
    hotstar_catalog.py   (already exists)
    sonyliv_catalog.py
    zee5_catalog.py

Every platform's catalog module must export:
    PLATFORM   str             e.g. "SonyLIV"
    COLUMNS    list[str]       ordered output columns
    crawl(url, out_csv, raw_path, append, delay) -> pd.DataFrame
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

MAX_DEPTH = 30   # recursion guard

# ── shared output columns (superset of all three platforms) ─────────────────
COMMON_COLUMNS = [
    # identity
    "platform", "rail", "page", "section",
    "content_id", "series_id",
    # titles
    "title", "series_title", "episode_title",
    # classification
    "content_type",        # Movie / Show / Episode / Match / Clip / Live / Trailer
    "content_subtype",     # e.g. "T20", "Serie A", "Reality"
    "is_live",
    # meta
    "description",
    "year", "release_date",
    "rating", "duration_sec", "duration_label",
    "season_number", "episode_number", "episode_count",
    # sport-specific
    "sport",               # Cricket / Football / Tennis …
    "tournament",          # UEFA Champions League …
    "match_status",        # upcoming / live / completed
    "match_start_utc",
    "teams",               # "India vs Australia"
    # content meta
    "primary_genre", "genre_tags",
    "languages", "original_language", "available_languages", "language_count",
    # access
    "is_free", "subscription_required", "pay_per_view",
    # placement
    "found_in",            # "Sports > Cricket > ICC Champions Trophy"
    "detail_url",
    "poster_url",
    # scrape book-keeping
    "scraped_at",
]


# ── generic helpers ───────────────────────────────────────────────────────────

def find_key(node, key: str, _d: int = 0):
    """First value for `key` anywhere inside node. Depth-capped."""
    if _d > MAX_DEPTH:
        return None
    if isinstance(node, dict):
        if key in node:
            return node[key]
        for v in node.values():
            r = find_key(v, key, _d + 1)
            if r is not None:
                return r
    elif isinstance(node, list):
        for v in node:
            r = find_key(v, key, _d + 1)
            if r is not None:
                return r
    return None


def safe_get(d: dict, *keys, default=None):
    for k in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(k, default)
    return d


DURATION_RE = re.compile(r"(\d+)\s*h.*?(\d+)?\s*m?", re.I)

def secs(label: str | None) -> int | None:
    """Parse a human duration label like '1h 30m' or '90 min' into seconds."""
    if not label:
        return None
    m = DURATION_RE.search(str(label))
    if m:
        h = int(m.group(1) or 0)
        mi = int(m.group(2) or 0)
        return h * 3600 + mi * 60
    if re.search(r"\d+", str(label)):
        digits = int(re.search(r"\d+", str(label)).group())
        return digits * 60  # assume minutes
    return None


# ── save ─────────────────────────────────────────────────────────────────────

def save(rows: list[dict], out: str, columns: list[str] | None = None) -> pd.DataFrame:
    cols = columns or COMMON_COLUMNS
    df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=cols)
    df = df.reindex(columns=cols)
    df = df.drop_duplicates(subset=["platform", "content_id", "rail"], keep="first")
    df["scraped_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    df.to_csv(out, index=False)
    u = df["content_id"].nunique()
    print(f"  [{df['platform'].iloc[0] if not df.empty else '?'}] "
          f"{len(df)} rows / {u} unique titles → {out}")
    if not df.empty and "content_type" in df.columns:
        print("  types:", df["content_type"].value_counts().to_dict())
    return df


# ── Browser wrapper (shared across platforms) ────────────────────────────────

class Browser:
    """
    Playwright wrapper that fires on_json(url, data) for every JSON response.
    Each platform catalog passes its own handler.
    """

    def __init__(self, on_json, raw_path: str | None = None,
                 append: bool = True, headed: bool = False, delay: float = 1.5):
        self._on_json  = on_json
        self.headed    = headed
        self.delay     = delay
        self._seen: set = set()

        if raw_path:
            rp = Path(raw_path)
            if rp.exists() and not append:
                print(f"  ⚠  {raw_path} exists — appending (pass append=False to overwrite)")
            self.raw = open(raw_path, "a", encoding="utf-8")
        else:
            self.raw = None

    def start(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise SystemExit("pip install playwright pandas && playwright install chromium")
        self._pw      = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=not self.headed)
        self.page     = self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        ).new_page()
        self.page.on("response", self._handle)

    def _handle(self, resp):
        try:
            ct = resp.headers.get("content-type", "")
            if "json" not in ct:
                return
            data = resp.json()
            if self.raw:
                self.raw.write(json.dumps({"url": resp.url, "data": data}) + "\n")
            self._on_json(resp.url, data)
        except Exception:
            pass

    def visit(self, url: str, deep: bool = True, retries: int = 2) -> None:
        for attempt in range(retries + 1):
            try:
                self.page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                try:
                    self.page.wait_for_load_state("networkidle", timeout=10_000)
                except Exception:
                    pass
                if deep:
                    idle = 0
                    for _ in range(60):
                        before = len(self._seen)
                        self.page.mouse.wheel(0, 3_000)
                        self.page.wait_for_timeout(int(self.delay * 1_000))
                        idle = idle + 1 if len(self._seen) == before else 0
                        if idle >= 3:
                            break
                return
            except Exception as e:
                import time
                w = 2 ** attempt
                if attempt < retries:
                    print(f"    retry {attempt+1} for {url} ({e}) in {w}s")
                    time.sleep(w)
                else:
                    print(f"    ✗ gave up on {url}: {e}")

    def touch(self, key: str) -> bool:
        """Return True (and mark) if this key is new, False if already seen."""
        if key in self._seen:
            return False
        self._seen.add(key)
        return True

    def close(self):
        try:
            self._browser.close()
            self._pw.stop()
        finally:
            if self.raw:
                self.raw.close()

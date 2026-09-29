"""
catalog_base.py — shared types, helpers, parsers and output logic for all OTT scrapers.  (AUDITED)

Used by:
    hotstar_catalog.py   (not part of this audit — file was not supplied)
    sonyliv_catalog.py
    zee5_catalog.py

Every platform module exports:
    PLATFORM      str
    <Platform>Parser   (subclass of BaseParser)
    crawl(seeds, out, raw_path, append, delay, headed, debug, max_pages) -> pd.DataFrame
    parse_file(raw_path, out) -> pd.DataFrame

Design rules applied in this version
------------------------------------
* "Unknown" is never turned into a real value: missing access info is None/blank,
  not "subscription required"; missing original language is None, not "first language".
* Falsy-but-valid values (0, False) are kept — see first_present().
* Nothing fails silently: parse errors are counted and reported.
"""

from __future__ import annotations

import json
import re
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

MAX_DEPTH = 30   # recursion guard

# ── shared output columns ────────────────────────────────────────────────────
COMMON_COLUMNS = [
    # identity
    "platform", "rail", "page", "section",
    "content_id", "series_id",
    # titles
    "title", "series_title", "episode_title",
    # classification
    "content_type",        # Movie / Show / Episode / Match / Clip / Live / Trailer
    "content_subtype",
    "is_live",
    # meta
    "description",
    "year", "release_date",
    "rating", "duration_sec", "duration_label",
    "season_number", "episode_number", "episode_count",
    # sport-specific
    "sport",               # canonical name: Cricket / Football / Tennis …
    "sport_source",        # where the sport was detected: genre/title/rail/section/page
    "tournament",
    "match_status",
    "match_start_utc",     # ISO-8601 Z if the source had epoch or tz-aware time, else raw string
    "teams",
    # content meta
    "primary_genre", "genre_tags",
    "languages", "original_language", "available_languages", "language_count",
    # access  (True / False / blank = unknown)
    "is_free", "subscription_required", "pay_per_view",
    # placement
    "found_in",            # "<browsed page> > <rail>"
    "detail_url",
    "poster_url",
    # scrape book-keeping
    "scraped_at",
]

BOOL_COLS = ["is_live", "is_free", "subscription_required", "pay_per_view"]
INT_COLS = ["duration_sec", "year", "season_number", "episode_number",
            "episode_count", "language_count"]


# ── generic helpers ──────────────────────────────────────────────────────────

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


def safe_get(d, *keys, default=None):
    for k in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(k, default)
    return d


def first_present(*vals):
    """First value that is not None / empty string / empty container.
    Unlike an `a or b or c` chain this KEEPS 0 and False."""
    for v in vals:
        if v is None:
            continue
        if isinstance(v, str) and not v.strip():
            continue
        if isinstance(v, (list, dict, tuple, set)) and not v:
            continue
        return v
    return None


def as_text(v) -> str:
    return "" if v is None else str(v).strip()


_NAME_KEYS = ("name", "value", "title", "label", "display_name", "displayName", "id")


def _dict_name(d: dict) -> str | None:
    for k in _NAME_KEYS:
        if d.get(k) not in (None, ""):
            return str(d[k]).strip()
    return None


def as_str_list(value) -> list[str]:
    """Normalise genres / languages that may be a comma string, list of str,
    list of dicts ({"id":..,"value":..}) or a single dict. De-duplicated, order kept."""
    if value is None:
        return []
    if isinstance(value, str):
        return [p.strip() for p in re.split(r"[,;|]", value) if p.strip()]
    if isinstance(value, dict):
        n = _dict_name(value)
        return [n] if n else []
    if isinstance(value, (list, tuple, set)):
        out: list[str] = []
        for v in value:
            for s in as_str_list(v):
                if s not in out:
                    out.append(s)
        return out
    return [str(value)]


def teams_text(value) -> str | None:
    """'A vs B' from a list of names/dicts, or the string as given."""
    if not value:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, (list, tuple)):
        names = []
        for t in value[:2]:
            n = _dict_name(t) if isinstance(t, dict) else as_text(t)
            if n:
                names.append(n)
        return " vs ".join(names) or None
    return as_text(value) or None


def absolute_url(value, base: str) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    if value.startswith("http"):
        return value
    return base + "/" + value.lstrip("/")


def to_bool(v):
    """True / False / None (unknown). Understands 0/1 and 'true'/'false' strings."""
    if v is None or v is pd.NA:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return None if v != v else bool(v)
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("true", "1", "yes", "y", "t"):
            return True
        if s in ("false", "0", "no", "n", "f"):
            return False
    return None


# ── duration ─────────────────────────────────────────────────────────────────

_CLOCK_RE = re.compile(r"^\s*(?:(\d+):)?(\d{1,2}):(\d{2})\s*$")          # H:MM:SS or MM:SS
_UNIT_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*"
    r"(hours|hour|hrs|hr|h|minutes|minute|mins|min|m|seconds|second|secs|sec|s)(?![a-z])",
    re.I,
)
_UNIT_SECS = {"h": 3600, "m": 60, "s": 1}


def secs(label, bare_unit: str = "min") -> int | None:
    """Duration → seconds.

    Handles '1h 30m', '1h', '90m', '45 min', '2 hrs 5 mins', '1:30:00', '45:30'.
    A bare number in a *string label* is read as minutes (bare_unit='min');
    a real int/float is read as seconds.
    """
    if label is None or isinstance(label, bool):
        return None
    if isinstance(label, (int, float)):
        return int(label) if label >= 0 else None
    s = str(label).strip()
    if not s:
        return None
    m = _CLOCK_RE.match(s)
    if m:
        return int(m.group(1) or 0) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
    hits = _UNIT_RE.findall(s)
    if hits:
        return int(sum(float(n) * _UNIT_SECS[u.lower()[0]] for n, u in hits))
    if re.fullmatch(r"\d+", s):
        return int(s) * (60 if bare_unit == "min" else 1)
    return None


def duration_to_sec(value=None, label=None) -> int | None:
    """`value` = the API's numeric duration field (ASSUMED SECONDS — verify per platform);
    `label` = human label used only if `value` is absent/unparseable."""
    v = first_present(value)
    if v is not None and not isinstance(v, bool):
        if isinstance(v, (int, float)):
            return int(v) if v >= 0 else None
        if isinstance(v, str):
            s = v.strip()
            if re.fullmatch(r"\d+(\.\d+)?", s):
                return int(float(s))
            r = secs(s)
            if r is not None:
                return r
    return secs(label) if label is not None else None


# ── timestamps ───────────────────────────────────────────────────────────────

_ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"


def to_utc_iso(v) -> str | None:
    """Epoch (s or ms) or tz-aware string → ISO-8601 UTC.
    A tz-less string cannot be proven UTC, so it is returned untouched."""
    if v is None or isinstance(v, bool) or (isinstance(v, str) and not v.strip()):
        return None
    if isinstance(v, (int, float)) or (isinstance(v, str) and re.fullmatch(r"\d{9,13}", v.strip())):
        n = float(v)
        if n > 1e11:
            n /= 1000.0
        try:
            return datetime.fromtimestamp(n, tz=timezone.utc).strftime(_ISO_FMT)
        except (OverflowError, OSError, ValueError):
            return None
    s = str(v).strip()
    try:
        ts = pd.to_datetime(s, errors="coerce")
    except Exception:
        return s
    if ts is pd.NaT or pd.isna(ts):
        return s
    if ts.tzinfo is not None:
        return ts.tz_convert("UTC").strftime(_ISO_FMT)
    return s


# ── sport detection ──────────────────────────────────────────────────────────
# Word-boundary patterns (no substring hits like "Emma" → MMA).
_SPORT_PATTERNS = [
    ("Cricket",    r"\bcricket\b|\bipl\b|\bt20i?\b|\bodi\b|\btest match\b"),
    ("Football",   r"\bfootball\b|\bsoccer\b|\bserie a\b|\bla ?liga\b|\bbundesliga\b|\bligue 1\b|\buefa\b|\bfifa\b|\bisl\b"),
    ("Tennis",     r"\btennis\b|\bwimbledon\b|\batp\b|\bwta\b"),
    ("Kabaddi",    r"\bkabaddi\b|\bpkl\b"),
    ("Hockey",     r"\bhockey\b"),
    ("Badminton",  r"\bbadminton\b|\bbwf\b"),
    ("Wrestling",  r"\bwrestling\b|\bwwe\b"),
    ("MMA",        r"\bufc\b|\bmma\b"),
    ("Motorsport", r"\bformula ?(?:1|e|one)\b|\bf1\b|\bmotogp\b|\bmotorsports?\b|\bnascar\b"),
    ("Chess",      r"\bchess\b"),
    ("Golf",       r"\bgolf\b"),
    ("Basketball", r"\bbasketball\b|\bnba\b"),
    ("Volleyball", r"\bvolleyball\b"),
    ("Athletics",  r"\bathletics\b"),
    ("Archery",    r"\barchery\b"),
    ("Boxing",     r"\bboxing\b"),
    ("Kho Kho",    r"\bkho[\s_-]?kho\b"),
]
# Too ambiguous for titles ("Shooting Stars", "Racing Rani") → only trusted in genre fields.
_GENRE_ONLY_PATTERNS = [
    ("Shooting",   r"\bshooting\b"),
    ("Motorsport", r"\bracing\b"),
]
_SPORT_RES = [(n, re.compile(p, re.I)) for n, p in _SPORT_PATTERNS]
_GENRE_ONLY_RES = [(n, re.compile(p, re.I)) for n, p in _GENRE_ONLY_PATTERNS]


def _earliest(text: str, res) -> str | None:
    best = None
    for name, rx in res:
        m = rx.search(text)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), name)
    return best[1] if best else None


def detect_sport(genres, title, rail, page, section=None):
    """Return (canonical_sport, source) or (None, None).

    Sources are tried in priority order — genre, title, rail, section, page — and the
    FIRST source that yields a sport wins. So a Kabaddi clip in a 'Live Cricket' rail is
    Kabaddi (title/genre beat rail). `section` is used only when it looks like a path
    (starts with '/'), because opaque bucket IDs can contain tokens like 'f1'."""
    sources = [
        ("genre", " | ".join(genres or [])),
        ("title", title or ""),
        ("rail", rail or ""),
        ("section", section if isinstance(section, str) and section.startswith("/") else ""),
        ("page", page or ""),
    ]
    for src, text in sources:
        if not text:
            continue
        name = _earliest(text, _SPORT_RES)
        if not name and src == "genre":
            name = _earliest(text, _GENRE_ONLY_RES)
        if name:
            return name, src
    return None, None


# ── access model ─────────────────────────────────────────────────────────────
_PPV_RE = re.compile(r"tvod|ppv|rent|pay.?per", re.I)
_PAID_RE = re.compile(r"premium|svod|paid|subscri", re.I)
_FREE_RE = re.compile(r"free|avod|fvod|advert", re.I)


def parse_access(free_flag=None, mode=None, ppv_flag=None):
    """→ (is_free, subscription_required, pay_per_view); each True / False / None.

    Explicit boolean flag wins; otherwise the textual access mode is classified.
    If neither is present everything stays None (UNKNOWN) — it is never guessed."""
    is_free = to_bool(free_flag)
    ppv = to_bool(ppv_flag)
    m = as_text(mode)
    if is_free is None and m:
        if _PPV_RE.search(m):
            is_free, ppv = False, True
        elif _PAID_RE.search(m):
            is_free = False
        elif _FREE_RE.search(m):
            is_free = True
    if is_free is None:
        return None, None, ppv
    if ppv is None:
        ppv = False
    sub_required = (not is_free) and (not ppv)
    return is_free, sub_required, ppv


# ── save ─────────────────────────────────────────────────────────────────────

def save(rows: list[dict], out: str, columns: list[str] | None = None,
         platform: str | None = None) -> pd.DataFrame:
    cols = columns or COMMON_COLUMNS
    df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=cols)
    df = df.reindex(columns=cols)
    df = df.drop_duplicates(subset=["platform", "page", "rail", "content_id"], keep="first")
    for c in BOOL_COLS:
        df[c] = df[c].map(to_bool).astype("boolean")
    for c in INT_COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce").round().astype("Int64")
    df["scraped_at"] = datetime.now(timezone.utc).strftime(_ISO_FMT)
    df.to_csv(out, index=False)
    label = platform or (df["platform"].iloc[0] if not df.empty else "?")
    print(f"  [{label}] {len(df)} rows / {df['content_id'].nunique()} unique titles → {out}")
    if df.empty:
        print(f"  ⚠  [{label}] ZERO rows written — nothing was captured. "
              f"Re-run with --headed --debug to see what the site returns.")
    else:
        print("  types:", df["content_type"].value_counts().to_dict())
    return df


# ── shared parser base ───────────────────────────────────────────────────────
SPORT_SLUG_RE = re.compile(
    r"^(?:/[a-z]{2})?/(?:custompage/sports|sports|sports-games|sport)[\w\-/]*$", re.I)
MAX_SLUG_SEGMENTS = 3      # /sports/games ok; /sports/games/live-streaming/<id>/<match> is a detail page


class BaseParser:
    """Common state for platform parsers.

    current_page : the page slug the browser is on (set by crawl() / read from the raw
                   file). Used for `page` and `found_in`; if unknown, falls back to
                   'api:<path>' so it is obvious the label is NOT a browsed page.
    """

    def __init__(self):
        self.rows: list[dict] = []
        self.seen: set = set()
        self.slugs: set = set()
        self.current_page: str | None = None

    def page_for(self, url: str) -> str:
        if self.current_page:
            return self.current_page
        m = re.match(r"https?://[^/]+(/[^?#]*)?", url)
        return "api:" + ((m.group(1) if m and m.group(1) else "/"))

    def add(self, row: dict | None) -> bool:
        if not row:
            return False
        key = (row["page"], row["rail"], row["content_id"])
        if key in self.seen:
            return False
        self.seen.add(key)
        self.rows.append(row)
        return True

    def maybe_slug(self, value) -> None:
        """Queue a same-site sports page for crawling — only clean sports paths."""
        if isinstance(value, str):
            v = value.split("?")[0].split("#")[0]
            v = v.rstrip("/") or "/"
            segs = [x for x in v.split("/") if x]
            if segs and re.fullmatch(r"[a-z]{2}", segs[0]) and len(segs) > 1:
                segs = segs[1:]                                  # drop locale prefix like /en
            if len(v) < 120 and len(segs) <= MAX_SLUG_SEGMENTS and SPORT_SLUG_RE.match(v):
                self.slugs.add(v)


def reparse(parser: BaseParser, raw_path: str) -> None:
    """Feed a saved JSONL through parser.parse(). Bad lines are counted, not fatal."""
    if not Path(raw_path).exists():
        raise SystemExit(f"raw file not found: {raw_path}")
    n = bad = 0
    with open(raw_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            n += 1
            try:
                d = json.loads(line)
                url, data = d["url"], d["data"]
            except (ValueError, KeyError, TypeError):
                bad += 1
                continue
            parser.current_page = d.get("page")
            try:
                parser.parse(url, data)
            except Exception as e:                       # noqa: BLE001
                bad += 1
                if bad <= 3:
                    print(f"    parse error on {url[:90]}: {type(e).__name__}: {e}")
    parser.current_page = None
    if n == 0:
        print(f"  ⚠  {raw_path} is EMPTY — the earlier crawl captured no JSON.")
    if bad:
        print(f"  ⚠  {bad} of {n} raw records could not be parsed")


# ── Browser wrapper ──────────────────────────────────────────────────────────

class Browser:
    """
    Playwright wrapper that calls on_json(url, data) for every JSON response.

    current_page : set by the crawler before each visit(); stored in each raw record
                   so a later re-parse knows which page the response belonged to.
    n_json       : number of JSON responses captured (drives scroll idle detection).
    debug        : print every captured/blocked response so an empty scrape can be diagnosed.
    """

    def __init__(self, on_json, raw_path: str | None = None, append: bool = True,
                 headed: bool = False, delay: float = 1.5, debug: bool = False,
                 raw_filter=None, headless_new: bool = False):
        self._on_json = on_json
        self.headless_new = headless_new    # only used when headed=False: Chrome "new headless" mode
        self.blocked_docs = 0               # 401/403/429 on page documents (bot-block signal)
        self.raw_filter = raw_filter        # callable(url)->bool; False = ignore (trackers etc.)
        self.headed = headed
        self.delay = delay
        self.debug = debug
        self._seen: set = set()
        self.n_json = 0
        self.n_errors = 0
        self.current_page: str | None = None
        self._pw = None
        self._browser = None

        if raw_path:
            # append=False now truly overwrites (old code always appended)
            self.raw = open(raw_path, "a" if append else "w", encoding="utf-8")
        else:
            self.raw = None

    def start(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise SystemExit("pip install playwright pandas && playwright install chromium")
        self._pw = sync_playwright().start()
        kw = dict(headless=not self.headed,
                  args=["--disable-blink-features=AutomationControlled"])
        if not self.headed and self.headless_new:
            kw["channel"] = "chromium"      # new headless (needs a recent playwright); closer to real Chrome
        self._browser = self._pw.chromium.launch(**kw)
        ctx = self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            viewport={"width": 1440, "height": 900},
        )
        self.page = ctx.new_page()
        self.page.on("response", self._handle)

    def _handle(self, resp):
        try:
            ct = (resp.headers.get("content-type") or "").lower()
            rtype = getattr(resp.request, "resource_type", "")
            if resp.status in (401, 403, 429) and rtype == "document":
                self.blocked_docs += 1
            if resp.status in (401, 403, 429) and rtype in ("document", "xhr", "fetch"):
                print(f"    ⚠ HTTP {resp.status} on {rtype}: {resp.url[:110]}  (possible block / geo-restriction)")
            if "json" not in ct and rtype not in ("xhr", "fetch"):
                return
            if self.raw_filter and not self.raw_filter(resp.url):
                return
            try:
                data = resp.json()
            except Exception:
                return                                    # not JSON / body unavailable
            self.n_json += 1
            if self.debug:
                print(f"    [json] {resp.status} {ct.split(';')[0]} {resp.url[:110]}")
            if self.raw:
                self.raw.write(json.dumps({"url": resp.url, "page": self.current_page,
                                           "data": data}) + "\n")
                self.raw.flush()
            self._on_json(resp.url, data)
        except Exception as e:                            # noqa: BLE001
            self.n_errors += 1
            if self.n_errors <= 5:
                print(f"    handler error: {type(e).__name__}: {e}")
                if self.debug:
                    traceback.print_exc()

    def visit(self, url: str, deep: bool = True, retries: int = 2) -> bool:
        for attempt in range(retries + 1):
            try:
                self.page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                try:
                    self.page.wait_for_load_state("networkidle", timeout=10_000)
                except Exception:
                    pass
                if deep:
                    idle = 0
                    last_h = -1
                    for _ in range(60):
                        before = self.n_json
                        self.page.mouse.wheel(0, 3_000)
                        self.page.wait_for_timeout(int(self.delay * 1_000))
                        try:
                            h = self.page.evaluate("document.body.scrollHeight")
                        except Exception:
                            h = last_h
                        grew = h != last_h
                        last_h = h
                        idle = idle + 1 if (self.n_json == before and not grew) else 0
                        if idle >= 3:
                            break
                return True
            except Exception as e:                        # noqa: BLE001
                w = 2 ** attempt
                if attempt < retries:
                    print(f"    retry {attempt + 1} for {url} ({e}) in {w}s")
                    time.sleep(w)
                else:
                    print(f"    ✗ gave up on {url}: {e}")
        return False

    def page_links(self) -> list[str]:
        """All same-page <a href> values (relative or absolute), for sport-page discovery."""
        try:
            return self.page.eval_on_selector_all(
                "a[href]", "els => els.map(e => e.getAttribute('href'))") or []
        except Exception:
            return []

    def touch(self, key: str) -> bool:
        """Return True (and mark) if this key is new, False if already seen."""
        if key in self._seen:
            return False
        self._seen.add(key)
        return True

    def close(self):
        try:
            if self._browser:
                self._browser.close()
            if self._pw:
                self._pw.stop()
        finally:
            if self.raw:
                self.raw.close()

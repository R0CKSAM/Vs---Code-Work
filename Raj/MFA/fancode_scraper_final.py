"""
FanCode schedule scraper  -  FINAL
--------------------------------
Fixes over v1 (found by inspecting your output files):
  * Only 2 days came back  -> v1 stopped scrolling too early and never clicked
    date tabs / "load more". v2 scrolls until nothing new arrives, clicks date
    tabs / next arrows / load-more buttons, AND replays the site's own API
    calls day-by-day across the whole date range.
  * The same 16 cricket matches were copied into 6 other sports -> v2 tags each
    match with its own sport and drops matches that belong to another sport.
  * "event name" was empty -> v2 reads tournament / series / league from the
    match or from its parent object.
  * "match" showed T20I / TEST (that is the format) -> v2 uses match number /
    round; if the site gives none, it numbers matches inside each event
    (Match 1, Match 2 ...) in date order. Format goes into "any details".
  * Badminton rows had round/venue as "countries" -> v2 prefers real
    participant lists.

SETUP (once):      py -m pip install playwright openpyxl
                   py -m playwright install chromium
RUN:               py fancode_scraper_final.py
FIRST RUN ADVICE:  py fancode_scraper_final.py --show --debug
OPTIONS:           --only Cricket,Golf         scrape just some sports
                   --no-replay                 skip the day-by-day API replay
"""

import argparse
import json
import re
import sys
import time
import functools
import traceback
from collections import defaultdict, Counter
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode, quote
from datetime import datetime, date, time as dtime, timedelta, timezone

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from playwright.sync_api import sync_playwright

print = functools.partial(print, flush=True)   # show progress immediately

# ----------------------------------------------------------------- CONFIG --
SPORTS = [
    ("Cricket", "cricket"),
    ("Football", "football"),
    ("Formula 1", "formula1"),
    ("Tennis", "lawn-tennis"),
    ("MotoGP", "motogp"),
    ("Golf", "golf"),
    ("Motorsports", "racing"),
    ("Badminton", "badminton"),
]
BASE = "https://www.fancode.com/{slug}/schedule"
DATE_START = date.today()
DATE_END = date(2027, 8, 4)
IST = timezone(timedelta(hours=5, minutes=30))

MAX_SCROLL_ROUNDS = 80
STAGNANT_LIMIT = 5            # stop scrolling after this many rounds with nothing new
SCROLL_PAUSE_MS = 1500
STALE_DAYS = 21               # date replay: stop after this many days with no NEW matches
STALE_PAGES = 3               # page replay: stop after this many pages with no NEW matches
REPLAY_BUDGET_S = 420         # max seconds spent replaying one API call
REPLAY_DELAY_S = 0.1

SPORT_HEADERS = ["event name", "match", "date", "time (IST)", "title", "venue",
                 "format", "country 1", "country 2", "status", "result",
                 "other details"]
DATE_HEADERS = ["date", "sport", "event name", "match", "time (IST)", "title",
                "venue", "format", "country 1", "country 2", "status", "result",
                "other details"]
NON_TEAM_SLUGS = {"formula1", "motogp", "golf", "racing"}   # no "A vs B" matches

START_KEYS = ["startTime", "start_time", "startDate", "matchStartTime",
              "startTimeStamp", "startTimestamp", "scheduledAt", "startsAt",
              "matchDate", "scheduledTime", "start", "date"]
NAME_KEYS = ["matchName", "name", "title", "shortName", "matchTitle"]
STATUS_KEYS = ["status", "matchStatus", "state", "liveStatus"]
RESULT_KEYS = ["result", "resultText", "matchResult", "resultSummary", "statusNote",
               "statusText", "matchSummary", "winnerName", "winner", "summary", "outcome"]
VENUE_KEYS = ["venue", "stadium", "location", "ground", "city"]
FORMAT_KEYS = ["matchType", "matchFormat", "format", "gameType"]
LABEL_KEYS = ["matchNumber", "matchNo", "match_number", "matchLabel", "matchOrder"]
TEAM_LIST_KEYS = ["teams", "participants", "competitors", "squads", "players",
                  "sides", "contestants", "athletes", "entrants", "opponents"]
TEAM_PAIRS = [("team1", "team2"), ("teamA", "teamB"), ("homeTeam", "awayTeam"),
              ("home", "away"), ("player1", "player2"), ("firstTeam", "secondTeam"),
              ("participant1", "participant2")]
SPORT_KEYS = ["sport", "sportName", "sportsName", "sportSlug", "sportType",
              "sportsType"]


# ---------------------------------------------------------------- HELPERS --
def to_text(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return ""
    if isinstance(v, (str, int, float)):
        return str(v).strip()
    if isinstance(v, dict):
        for k in ("name", "title", "shortName", "displayName", "fullName",
                  "text", "message", "label"):
            if k in v and isinstance(v[k], (str, int, float)) and str(v[k]).strip():
                return str(v[k]).strip()
        return ""
    if isinstance(v, list):
        return ", ".join(t for t in (to_text(x) for x in v) if t)
    return ""


def first(obj, keys):
    for k in keys:
        if k in obj:
            t = to_text(obj[k])
            if t:
                return t
    return ""


def parse_dt(v):
    """Epoch (s/ms) or ISO string -> aware datetime in IST, else None."""
    if v is None or isinstance(v, bool):
        return None
    try:
        if isinstance(v, (int, float)) or (
                isinstance(v, str) and re.fullmatch(r"\d{9,13}(\.\d+)?", v.strip())):
            n = float(v)
            if n > 1e11:
                n /= 1000.0
            if n < 1e9:
                return None
            return datetime.fromtimestamp(n, tz=IST)
        if isinstance(v, str):
            s = v.strip().replace("Z", "+00:00")
            if not re.match(r"\d{4}-\d{2}-\d{2}", s):
                return None
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=IST)
            return dt.astimezone(IST)
    except Exception:
        return None
    return None


def get_start(obj):
    for k in START_KEYS:
        if k in obj:
            dt = parse_dt(obj[k])
            if dt:
                return dt
    return None


VS_RE = re.compile(r"\s+(?:vs\.?|v/s|v)\s+", re.I)
TEAMISH_KEY_RE = re.compile(r"team|player|participant|competitor|side|squad|opponent|"
                            r"athlete|entrant|pair|contestant", re.I)


def get_teams(obj, name, avoid=None):
    """Two competitor names. 'avoid' = texts (title, venue) that are NOT competitors."""
    avoid = {a.lower() for a in (avoid or ()) if a}

    def ok(t):
        return bool(t) and t.lower() not in avoid

    for k in TEAM_LIST_KEYS:
        v = obj.get(k)
        if isinstance(v, list) and len(v) >= 2:
            t = [x for x in (to_text(i) for i in v) if ok(x)]
            if len(t) >= 2:
                return t[0], t[1]
    for a, b in TEAM_PAIRS:
        if a in obj and b in obj:
            x, y = to_text(obj[a]), to_text(obj[b])
            if ok(x) and ok(y):
                return x, y
    m = VS_RE.split(name or "", maxsplit=1)
    if len(m) == 2 and m[0].strip() and m[1].strip():
        return m[0].strip(), m[1].strip()
    return "", ""


def deep_pair(obj, avoid, depth=0):
    """Last resort: a team/player-like list of 2+ named items anywhere inside."""
    for k, v in obj.items():
        if isinstance(v, list) and len(v) >= 2 and TEAMISH_KEY_RE.search(k) \
                and all(isinstance(i, dict) for i in v[:2]):
            names = [n for n in (to_text(i) for i in v) if n and n.lower() not in avoid]
            if len(names) >= 2:
                return names[0], names[1]
        elif isinstance(v, dict) and depth < 2:
            r = deep_pair(v, avoid, depth + 1)
            if r:
                return r
    return None


def looks_like_match(obj):
    if not isinstance(obj, dict) or get_start(obj) is None:
        return False
    a, b = get_teams(obj, first(obj, NAME_KEYS))
    return bool(a and b)


def sport_of(obj):
    if not isinstance(obj, dict):
        return ""
    for k in SPORT_KEYS:
        if k in obj:
            t = to_text(obj[k]).lower()
            if t and not t.isdigit():
                return t
    return ""


EVENT_PATTERNS = [r"^tour", r"tournament", r"series", r"league", r"competition",
                  r"championship", r"event", r"season|cup"]
EVENT_BAD_KEY_RE = re.compile(r"(id|ids|slug|url|image|img|logo|icon|banner|count|status|"
                              r"type|format|color|colour|key|code|time|date|flag|desc|"
                              r"order|rank|number|no)$", re.I)
EVENT_BAD_VAL_RE = re.compile(
    r"^(today|tomorrow|yesterday|live( now)?|upcoming|completed|results?|recent|all|"
    r"schedule|matches|fixtures|cricket|football|soccer|formula ?1|f1|tennis|lawn tennis|"
    r"motogp|golf|motorsports?|racing|badminton)$|schedule|^\d{1,2}\s*[A-Za-z]{3}\b", re.I)


def clean_event(t):
    t = (t or "").strip()
    if len(t) < 3 or not re.search(r"[A-Za-z]", t):
        return ""
    if re.fullmatch(r"[\d\-a-fA-F:_]{6,}", t) or EVENT_BAD_VAL_RE.search(t):
        return ""
    return t


def event_from_own_keys(obj):
    """Tournament / series name stored on the match itself (text or {name: ..})."""
    for pat in EVENT_PATTERNS:
        for k, v in obj.items():
            if re.search(pat, k, re.I) and not EVENT_BAD_KEY_RE.search(k):
                t = clean_event(to_text(v))
                if t:
                    return t
    return ""


def event_from_container(obj):
    """A parent dict that holds a list of matches and has its own name."""
    for k, v in obj.items():
        if isinstance(v, list) and v and any(
                isinstance(i, dict) and looks_like_match(i) for i in v[:3]):
            for key in ("tourName", "tournamentName", "seriesName", "leagueName",
                        "competitionName", "eventName", "tour", "tournament",
                        "name", "title"):
                t = clean_event(to_text(obj.get(key)))
                if t:
                    return t
    return ""


def walk(node, out, ctx):
    if isinstance(node, dict):
        new = dict(ctx)
        sp = sport_of(node)
        if sp:
            new["sport"] = sp
        if looks_like_match(node):
            own = event_from_own_keys(node)
            if own:
                new["event"] = own
            out.append((node, new))
            for v in node.values():
                walk(v, out, new)
            return
        ev = event_from_container(node)
        if ev:
            new["event"] = ev
        for v in node.values():
            walk(v, out, new)
    elif isinstance(node, list):
        for v in node:
            walk(v, out, ctx)


ALIASES = {
    "cricket": {"cricket"}, "football": {"football", "soccer"},
    "formula1": {"formula1", "f1", "formulaone"}, "lawn-tennis": {"tennis", "lawntennis"},
    "motogp": {"motogp"}, "golf": {"golf"},
    "racing": {"racing", "motorsports", "motorsport"}, "badminton": {"badminton"},
}
GENERIC_MOTOR = {"racing", "motorsports", "motorsport"}


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def sport_matches(found, name, slug):
    """True = belongs here, False = belongs to another sport, None = unknown."""
    if not found:
        return None
    f = _norm(found)
    mine = {_norm(name), _norm(slug)} | ALIASES.get(slug, set())
    if f in mine:
        return True
    if slug in ("formula1", "motogp") and f in GENERIC_MOTOR:
        return True          # generic parent tag, keep
    for other, al in ALIASES.items():
        if other != slug and f in al:
            return False
    return None


RESULT_KEY_RE = re.compile(r"result|summary|outcome|status(text|note|msg|message)|"
                           r"matchnote|winmessage|won", re.I)
OTHER_FIELDS = [("Round", ["round", "roundName"]), ("Stage", ["stage", "stageName"]),
                ("Description", ["description", "subTitle", "subtitle", "matchDescription"])]


def result_text(obj):
    t = first(obj, RESULT_KEYS)
    if t:
        return t
    for k, v in obj.items():
        if RESULT_KEY_RE.search(k) and not EVENT_BAD_KEY_RE.search(k):
            tv = to_text(v)
            if len(tv) > 3 and tv.lower() not in ("true", "false", "null", "none"):
                return tv
    return ""


def row_key(r):
    return r["_id"] or (r["dt"].isoformat(), r["country 1"], r["country 2"],
                        r["title"], r["venue"])


def normalise(obj, ctx, sport, slug=""):
    dt = get_start(obj)
    title = first(obj, NAME_KEYS)
    venue = first(obj, VENUE_KEYS)
    non_team = slug in NON_TEAM_SLUGS
    avoid = {title, venue}

    t1 = t2 = ""
    if not non_team or VS_RE.search(title):
        t1, t2 = get_teams(obj, title, avoid)
        if not t1 and not non_team:
            pr = deep_pair(obj, {a.lower() for a in avoid if a})
            if pr:
                t1, t2 = pr
    has_teams = bool(t1 and t2)

    # sub-name (e.g. "Free Practice 1" when the title is the series "DTM")
    alt = ""
    if not has_teams:
        raw1, _ = get_teams(obj, "", None)
        if raw1 and raw1 != title and raw1 != venue:
            alt = raw1

    label = ""
    for k in LABEL_KEYS:
        t = to_text(obj.get(k))
        if t:
            label = f"Match {t}" if t.isdigit() else t
            break
    match = label if has_teams else (alt or label or title)

    event = ctx.get("event", "")
    if not event and not has_teams:
        event = title if (alt and title != alt) else venue   # fallback: no tournament in data

    fmt = first(obj, FORMAT_KEYS) if slug == "cricket" else ""

    other = []
    for lab, keys in OTHER_FIELDS:
        t = first(obj, keys)
        if t and t not in (title, match, label, event) and not t.isdigit():
            other.append(f"{lab}: {t}")
        elif t and t.isdigit() and lab == "Round" and not non_team:
            other.append(f"Round: {t}")

    return {
        "dt": dt, "date": dt.date(), "sport": sport,
        "event name": event, "match": match,
        "time (IST)": dt.strftime("%H:%M"),
        "title": title, "venue": venue, "format": fmt,
        "country 1": t1, "country 2": t2,
        "status": first(obj, STATUS_KEYS), "result": result_text(obj),
        "other details": " | ".join(other),
        "_id": to_text(obj.get("id") or obj.get("matchId") or ""),
        "_found_sport": ctx.get("sport", ""),
        "_has_event": bool(ctx.get("event", "")),
        "_raw": obj,
    }


def extract_rows(payloads, sport, slug, check_sport=True):
    rows, seen = [], set()
    for payload in payloads:
        if payload is None:
            continue
        found = []
        walk(payload, found, {})
        for obj, ctx in found:
            ok = sport_matches(ctx.get("sport", ""), sport, slug)
            if check_sport and ok is False:   # belongs to a different sport
                continue
            r = normalise(obj, ctx, sport, slug)
            key = row_key(r)
            if key in seen:
                continue
            seen.add(key)
            rows.append(r)
    return rows


# ------------------------------------------------------- PAGE INTERACTION --
def click_loop(page, locator_factory, max_clicks, wait_ms=900):
    n = 0
    for _ in range(max_clicks):
        try:
            loc = locator_factory()
            if loc.count() == 0:
                break
            loc.first.click(timeout=2500)
            page.wait_for_timeout(wait_ms)
            n += 1
        except Exception:
            break
    return n


def interact(page, captured, broad=False):
    """Scroll + click everything that could reveal more days."""
    stagnant, last_h, last_n = 0, 0, 0
    for _ in range(MAX_SCROLL_ROUNDS):
        try:
            page.mouse.wheel(0, 4000)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        except Exception:
            pass
        page.wait_for_timeout(SCROLL_PAUSE_MS)
        h = page.evaluate("document.body.scrollHeight")
        if h == last_h and len(captured) == last_n:
            stagnant += 1
            if stagnant >= STAGNANT_LIMIT:
                break
        else:
            stagnant = 0
        last_h, last_n = h, len(captured)

    # "Load more / Show more / View all"
    click_loop(page, lambda: page.get_by_text(
        re.compile(r"^\s*(load|show|view|see)\s+(more|all)", re.I)), 40)

    # next / right-arrow buttons in date strips
    click_loop(page, lambda: page.locator(
        "button[aria-label*='next' i], [class*='next' i][role='button'], "
        "button[aria-label*='right' i], [class*='arrow' i][class*='right' i]"), 40, 700)

    # clickable date / weekday tabs (short text only; never click match cards)
    click_date_tabs(page, broad)


_MONTHS = {"jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "sept", "oct",
           "nov", "dec", "january", "february", "march", "april", "june", "july",
           "august", "september", "october", "november", "december"}
_WEEKDAYS = {"mon", "tue", "tues", "wed", "thu", "thur", "thurs", "fri", "sat", "sun",
             "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}


BROAD_TAB_RE = re.compile(
    r"^\s*((Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*\b|\d{1,2}\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|"
    r"Sep|Oct|Nov|Dec)|(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s*\d{1,2}\b|"
    r"Today|Tomorrow)", re.I)


def is_date_tab(txt):
    """'Today', 'Sat 10', '09 Oct', 'Today 09 Oct', 'Fri, 16 Oct' ... but never a team name."""
    toks = re.findall(r"[A-Za-z]+|\d+", txt)
    if not toks or len(toks) > 5:
        return False
    key = 0
    for t in toks:
        tl = t.lower()
        if tl in ("today", "tomorrow", "yesterday") or tl in _WEEKDAYS or tl in _MONTHS:
            key += 1
        elif t.isdigit() and len(t) <= 4:
            continue
        else:
            return False
    return key >= 1


def click_date_tabs(page, broad=False):
    base = page.url
    seen_txt = set()
    clicked = []
    loose = re.compile(r"^\s*(Mon|Tue|Wed|Thu|Fri|Sat|Sun|Today|Tomorrow|\d{1,2}\b|"
                       r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec))", re.I)
    try:
        loc = page.get_by_text(loose)
        cnt = min(loc.count(), 300)
    except Exception:
        return
    for i in range(cnt):
        try:
            el = loc.nth(i)
            txt = " ".join(el.inner_text(timeout=600).split())
        except Exception:
            continue
        if not txt or " vs " in txt.lower():
            continue
        if broad:
            # fallback pass: anything that STARTS like a date label (older behaviour that
            # reached all cricket dates); navigation guard below protects against cards
            if len(txt) > 40 or not BROAD_TAB_RE.match(txt):
                continue
        elif len(txt) > 20 or not is_date_tab(txt):
            continue
        key = txt.lower()
        if key in seen_txt:
            continue
        seen_txt.add(key)
        try:
            el.click(timeout=1500)
            clicked.append(txt)
            page.wait_for_timeout(900)
            if urlsplit(page.url).path != urlsplit(base).path:   # navigated away
                page.goto(base, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(1500)
        except Exception:
            pass
    print(f"   clicked {len(clicked)} date tabs: {clicked[:8]}")


# ---------------------------------------------------------- API REPLAY --
ISO_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
EPOCH_KEY_RE = re.compile(r"date|time|from|to|start|end|day", re.I)
END_KEY_RE = re.compile(r"(to|end|until|upto)", re.I)
PAGE_KEYS = {"page", "pageno", "pagenumber", "pageindex", "pagenum", "offset", "skip"}
LIMIT_KEYS = {"limit", "size", "pagesize", "first", "count", "perpage", "take"}
SKIP_HEADERS = {"cookie", "host", "content-length", "accept-encoding", "connection"}


def day_epoch(d, ms, end=False):
    dt = datetime(d.year, d.month, d.day, tzinfo=IST) + (timedelta(days=1) if end else timedelta())
    n = int(dt.timestamp())
    return n * 1000 if ms else n


def _walk(o, fn, hits):
    """Copy a JSON structure, passing every scalar through fn(key, value, parent)."""
    if isinstance(o, dict):
        out = {}
        for k, v in o.items():
            if isinstance(v, (dict, list)):
                out[k] = _walk(v, fn, hits)
            else:
                nv = fn(k, v, o)
                if nv != v or type(nv) is not type(v):
                    hits.append(k)
                out[k] = nv
        return out
    if isinstance(o, list):
        res = []
        for v in o:
            if isinstance(v, (dict, list)):
                res.append(_walk(v, fn, hits))
            else:
                nv = fn("", v, None)
                if nv != v:
                    hits.append("[]")
                res.append(nv)
        return res
    return o


def _date_fn(day):
    def fn(k, v, parent):
        if isinstance(v, bool):
            return v
        end = bool(END_KEY_RE.match(k or "")) and not (k or "").lower().startswith("start")
        if isinstance(v, str):
            if ISO_RE.match(v.strip()):
                return ISO_RE.sub(day.isoformat(), v, count=1)
            if re.fullmatch(r"\d{10}|\d{13}", v) and EPOCH_KEY_RE.search(k or ""):
                return str(day_epoch(day, len(v) == 13, end))
        elif isinstance(v, (int, float)):
            n = str(int(v))
            if len(n) in (10, 13) and EPOCH_KEY_RE.search(k or ""):
                return day_epoch(day, len(n) == 13, end)
        return v
    return fn


def _page_fn(i):
    def fn(k, v, parent):
        kl = (k or "").lower()
        if kl in PAGE_KEYS and isinstance(v, int) and not isinstance(v, bool):
            if kl in ("offset", "skip"):
                step = 0
                for lk, lv in (parent or {}).items():
                    if lk.lower() in LIMIT_KEYS and isinstance(lv, int):
                        step = lv
                        break
                return v + i * (step or 20)
            return v + i
        return v
    return fn


def transform(req, fn, require_hit=True):
    """Rewrite the request's query params and body with fn. -> (url, body) or None."""
    hits = []
    parts = urlsplit(req["url"])
    qs = []
    for k, v in parse_qsl(parts.query, keep_blank_values=True):
        vs = v.strip()
        if vs[:1] in ("{", "["):
            try:
                obj = json.loads(vs)
                v = json.dumps(_walk(obj, fn, hits), separators=(",", ":"), ensure_ascii=False)
            except Exception:
                pass
        else:
            nv = fn(k, v, None)
            if nv == v and vs.isdigit():
                nv = str(fn(k, int(vs), None))
            if nv != v:
                hits.append(k)
                v = nv
        qs.append((k, v))
    url = urlunsplit((parts.scheme, parts.netloc, parts.path,
                      urlencode(qs, quote_via=quote), parts.fragment))

    body = req["body"]
    if body:
        try:
            obj = json.loads(body)
            body = json.dumps(_walk(obj, fn, hits), separators=(",", ":"), ensure_ascii=False)
        except Exception:
            if ISO_RE.search(body):
                nb = ISO_RE.sub(lambda m: str(fn("", m.group(0), None)), body)
                if nb != body:
                    hits.append("body")
                    body = nb
    return (url, body) if (hits or not require_hit) else None


def _row_ids(rows):
    return {row_key(r) for r in rows}


def replay(page, templates, sport, slug, known):
    """Re-call each API for later days / pages. Stops when nothing new arrives."""
    extra = []
    for t in templates:
        mode, i, stale, added, calls = t["mode"], 0, 0, 0, 0
        t0 = time.time()
        limit = STALE_DAYS if mode == "date" else STALE_PAGES
        print(f"[{sport}] replay by {mode}: {t['url'][:80]}...")
        while True:
            i += 1
            if mode == "date":
                day = DATE_START + timedelta(days=i - 1)
                if day > DATE_END:
                    break
                fn = _date_fn(day)
            else:
                if i > 400:
                    break
                fn = _page_fn(i)
            var = transform(t, fn, require_hit=False)
            if not var:
                break
            url, body = var
            payload = None
            try:
                resp = page.request.fetch(
                    url, method=t["method"], data=body, timeout=20000,
                    headers={k: v for k, v in t["headers"].items()
                             if k.lower() not in SKIP_HEADERS and not k.startswith(":")})
                payload = resp.json() if resp.ok else None
            except Exception:
                payload = None
            calls += 1
            new = 0
            if payload is not None:
                ids = _row_ids(extract_rows([payload], sport, slug))
                fresh = ids - known
                if fresh:
                    known |= fresh
                    extra.append(payload)
                    new = len(fresh)
                    added += new
            stale = 0 if new else stale + 1
            if calls % 25 == 0:
                where = day.isoformat() if mode == "date" else f"page {i}"
                print(f"[{sport}]   ...{where}: {added} new matches so far")
            if stale >= limit:
                break
            if time.time() - t0 > REPLAY_BUDGET_S:
                print(f"[{sport}]   time budget reached, moving on")
                break
            time.sleep(REPLAY_DELAY_S)
        print(f"[{sport}]   done: {added} new matches from {calls} calls")
    return extra


# ---------------------------------------------------------------- SCRAPER --
def scrape_sport(page, sport, slug, debug, do_replay):
    url = BASE.format(slug=slug)
    payloads, requests_seen = [], []

    def on_response(resp):
        try:
            rq = resp.request
            ct = (resp.headers.get("content-type") or "")
            if "json" not in ct and "graphql" not in rq.url:
                return
            try:
                data = resp.json()
            except Exception:
                data = None                      # body not readable now; re-fetched later
            try:
                body = rq.post_data
            except Exception:
                body = None
            requests_seen.append({"url": rq.url, "method": rq.method, "body": body,
                                  "headers": rq.headers, "payload": data})
            if data is not None:
                payloads.append(data)
        except Exception:
            pass

    def refetch_missing():
        n = 0
        for r in requests_seen:
            if r["payload"] is None and n < 40:
                n += 1
                try:
                    resp = page.request.fetch(
                        r["url"], method=r["method"], data=r["body"], timeout=20000,
                        headers={k: v for k, v in r["headers"].items()
                                 if k.lower() not in SKIP_HEADERS and not k.startswith(":")})
                    if resp.ok:
                        r["payload"] = resp.json()
                        payloads.append(r["payload"])
                except Exception:
                    pass

    page.on("response", on_response)
    for attempt in (1, 2, 3):
        print(f"\n[{sport}] opening {url}" + (f"  (retry {attempt - 1})" if attempt > 1 else ""))
        try:
            page.goto(url, wait_until="networkidle", timeout=60000)
        except Exception as e:
            print(f"[{sport}] load warning: {str(e)[:120]}")
        page.wait_for_timeout(2500 + 2500 * (attempt - 1))      # let the page hydrate
        try:
            interact(page, payloads, broad=(attempt >= 2))
        except Exception as e:
            print(f"[{sport}] interaction warning: {str(e)[:120]}")
        refetch_missing()
        try:
            nd = page.evaluate("document.getElementById('__NEXT_DATA__') ? "
                               "document.getElementById('__NEXT_DATA__').textContent : null")
            if nd:
                payloads.append(json.loads(nd))
        except Exception:
            pass
        if extract_rows(payloads, sport, slug):
            break
        if attempt < 3:
            print(f"[{sport}] nothing found yet, reloading and trying again...")
            page.wait_for_timeout(3000)
    page.remove_listener("response", on_response)

    known = _row_ids(extract_rows(payloads, sport, slug))
    print(f"[{sport}] page itself gave {len(known)} matches")

    if do_replay:
        try:
            seen_t, templates = set(), []
            for r in requests_seen:
                if r["payload"] is None or not extract_rows([r["payload"]], sport, slug):
                    continue
                sig = re.sub(r"\d+", "#", r["url"] + "|" + (r["body"] or ""))
                if sig in seen_t:
                    continue
                seen_t.add(sig)
                if transform(r, _date_fn(date(2001, 1, 1))):
                    templates.append(dict(r, mode="date"))
                if transform(r, _page_fn(1)):
                    templates.append(dict(r, mode="page"))
            if templates:
                payloads.extend(replay(page, templates, sport, slug, known))
            else:
                print(f"[{sport}] no date/page-driven API call found (using page data only)")
        except KeyboardInterrupt:
            raise
        except Exception as e:
            # never lose what the page already gave us
            print(f"[{sport}] replay problem ({type(e).__name__}: {str(e)[:150]}); "
                  f"keeping the {len(known)} matches already collected")

    if debug:
        try:
            with open(f"debug_{slug}.json", "w", encoding="utf-8") as f:
                json.dump(payloads[:60], f, ensure_ascii=False)
            with open(f"debug_{slug}_apis.txt", "w", encoding="utf-8") as f:
                for r in requests_seen:
                    n = len(extract_rows([r["payload"]], sport, slug)) if r["payload"] else -1
                    f.write(f"{r['method']} {r['url']}  body={str(r['body'])[:300]}  matches={n}\n")
            with open(f"debug_{slug}_body.txt", "w", encoding="utf-8") as f:
                f.write(page.inner_text("body"))
        except Exception:
            pass

    rows = extract_rows(payloads, sport, slug)
    in_range = sorted((r for r in rows if DATE_START <= r["date"] <= DATE_END),
                      key=lambda r: r["dt"])
    if in_range:
        n_ev = len({r["event name"] for r in in_range if r["event name"]})
        n_real = sum(1 for r in in_range if r["_has_event"])
        print(f"[{sport}] {len(in_range)} matches, {in_range[0]['date']} -> "
              f"{in_range[-1]['date']}, {n_ev} events "
              f"({n_real} rows with a real tournament name)")
        if n_real < len(in_range):
            try:
                with open(f"sample_{slug}.json", "w", encoding="utf-8") as f:
                    json.dump([r["_raw"] for r in in_range[:3]], f, ensure_ascii=False, indent=1)
                print(f"[{sport}] tournament name not found for some rows -> "
                      f"saved sample_{slug}.json (send it to me if names look wrong)")
            except Exception:
                pass
    else:
        raw = extract_rows(payloads, sport, slug, check_sport=False)
        tags = Counter(r["_found_sport"] or "(none)" for r in raw).most_common(6)
        print(f"[{sport}] 0 matches in range. Diagnostics: {len(payloads)} JSON replies, "
              f"{len(raw)} matches before sport filter, {len(rows)} after, "
              f"sport tags seen: {tags}")
        try:
            with open(f"debug_{slug}_apis.txt", "w", encoding="utf-8") as f:
                for r in requests_seen:
                    n = len(extract_rows([r["payload"]], sport, slug)) if r["payload"] else -1
                    f.write(f"{r['method']} {r['url']}  body={str(r['body'])[:300]}  matches={n}\n")
            with open(f"debug_{slug}.json", "w", encoding="utf-8") as f:
                json.dump(payloads[:25], f, ensure_ascii=False)
            with open(f"debug_{slug}_body.txt", "w", encoding="utf-8") as f:
                f.write(page.inner_text("body"))
            print(f"[{sport}] saved debug_{slug}_apis.txt, debug_{slug}.json and "
                  f"debug_{slug}_body.txt - send me these 3 files")
        except Exception as e:
            print(f"[{sport}] could not save debug files: {e}")
    return in_range


# --------------------------------------------------------------- CLEAN-UP --
def remove_shared_noise(data):
    """A match with no sport tag that shows up under 3+ sports is a global
    widget, not that sport's schedule: keep it only in the first sport."""
    fp = defaultdict(list)
    for sport, rows in data.items():
        for r in rows:
            if not r["_found_sport"]:
                fp[row_key(r)].append(sport)
    drop = {k: v[0] for k, v in fp.items() if len(set(v)) >= 3}
    removed = 0
    for sport, rows in data.items():
        keep = []
        for r in rows:
            k = row_key(r)
            if k in drop and drop[k] != sport and not r["_found_sport"]:
                removed += 1
                continue
            keep.append(r)
        if rows and not keep:           # never wipe a whole sport
            keep = rows
            removed -= len(rows)
        data[sport] = keep
    if removed > 0:
        print(f"\nRemoved {removed} duplicate rows copied across sports.")


def fill_match_numbers(rows):
    """No match label from the site: number matches (Match 1, 2, 3 ...) inside each
    event; if there is no event name, inside each day."""
    groups = defaultdict(list)
    for r in rows:
        if not r["match"]:
            groups[r["event name"] or r["date"].isoformat()].append(r)
    for g in groups.values():
        for i, r in enumerate(sorted(g, key=lambda x: x["dt"]), 1):
            r["match"] = f"Match {i}"


def sport_order(rows):
    """Group rows by event (events ordered by their first match), then by time."""
    first_dt = {}
    for r in rows:
        if r["event name"]:
            first_dt[r["event name"]] = min(first_dt.get(r["event name"], r["dt"]), r["dt"])
    return sorted(rows, key=lambda r: (first_dt.get(r["event name"], r["dt"]),
                                       r["event name"], r["dt"]))


# ------------------------------------------------------------------ EXCEL --
def cell_value(r, h):
    if h == "date":
        return r["date"]
    if h == "time (IST)":
        return dtime(r["dt"].hour, r["dt"].minute)
    return r.get(h, "")


def style_sheet(ws, headers):
    fill = PatternFill("solid", fgColor="1F4E78")
    for c in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=c)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = fill
        cell.alignment = Alignment(vertical="center")
    for c, h in enumerate(headers, 1):
        width = max(len(h) + 2, 12)
        for row in ws.iter_rows(min_row=2, min_col=c, max_col=c):
            cell = row[0]
            if h == "date":
                cell.number_format = "DD-MMM-YYYY"
                width = max(width, 13)
            elif h == "time (IST)":
                cell.number_format = "HH:MM"
                width = max(width, 11)
            elif cell.value:
                width = min(max(width, len(str(cell.value)) + 2), 60)
        ws.column_dimensions[get_column_letter(c)].width = width
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions


def write_workbooks(data, sports):
    wb1 = Workbook()
    wb1.remove(wb1.active)
    for sport, _ in sports:
        ws = wb1.create_sheet(sport[:31])
        ws.append(SPORT_HEADERS)
        for r in sport_order(data.get(sport, [])):
            ws.append([cell_value(r, h) for h in SPORT_HEADERS])
        style_sheet(ws, SPORT_HEADERS)
    wb1.save("fancode_sportwise.xlsx")

    order = {name: i for i, (name, _) in enumerate(sports)}
    wb2 = Workbook()
    ws = wb2.active
    ws.title = "Date wise"
    ws.append(DATE_HEADERS)
    all_rows = sorted((r for rows in data.values() for r in rows),
                      key=lambda r: (r["dt"], order.get(r["sport"], 99)))
    for r in all_rows:
        ws.append([cell_value(r, h) for h in DATE_HEADERS])
    style_sheet(ws, DATE_HEADERS)
    wb2.save("fancode_datewise.xlsx")

    print(f"\nSaved fancode_sportwise.xlsx and fancode_datewise.xlsx "
          f"({len(all_rows)} matches)")
    for sport, _ in sports:
        rows = sorted(data.get(sport, []), key=lambda r: r["dt"])
        span = f"{rows[0]['date']} -> {rows[-1]['date']}" if rows else "-"
        print(f"  {sport:<11}{len(rows):>5}   {span}")


def scrape_pass(p, todo, headless, args, data):
    """Scrape each sport in its own fresh browser (no shared state between sports)."""
    for sport, slug in todo:
        browser = None
        try:
            kw = {"headless": headless}
            if args.edge:
                kw["channel"] = "msedge"
            browser = p.chromium.launch(**kw)
            ctx = browser.new_context(
                user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
                viewport={"width": 1366, "height": 900}, locale="en-IN")
            page = ctx.new_page()
            rows = scrape_sport(page, sport, slug, args.debug, not args.no_replay)
            if rows or not data.get(sport):
                data[sport] = rows
        except KeyboardInterrupt:
            raise
        except Exception as e:
            print(f"[{sport}] FAILED: {type(e).__name__}: {str(e)[:200]}")
            traceback.print_exc(limit=3)
            data.setdefault(sport, [])
        finally:
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", action="store_true", help="show the browser")
    ap.add_argument("--debug", action="store_true", help="save raw JSON / API log / HTML")
    ap.add_argument("--no-replay", action="store_true", help="skip day-by-day API replay")
    ap.add_argument("--only", default="", help="comma list, e.g. Cricket,Football")
    ap.add_argument("--edge", action="store_true", help="use installed Microsoft Edge")
    args = ap.parse_args()

    sports = SPORTS
    if args.only:
        want = {s.strip().lower() for s in args.only.split(",")}
        sports = [s for s in SPORTS if s[0].lower() in want]

    print(f"Range: {DATE_START} -> {DATE_END}")
    data = {}
    with sync_playwright() as p:
        try:
            scrape_pass(p, sports, not args.show, args, data)
            empties = [sl for sl in sports if not data.get(sl[0])]
            if empties:
                print("\nNo matches for: " + ", ".join(e[0] for e in empties) +
                      "\nRetrying them once in a VISIBLE browser window (do not close it)...")
                scrape_pass(p, empties, False, args, data)
        except KeyboardInterrupt:
            print("\nStopped by you (Ctrl+C) - saving what was collected so far...")
    for sport, _ in sports:
        data.setdefault(sport, [])

    remove_shared_noise(data)
    for rows in data.values():
        fill_match_numbers(rows)
    write_workbooks(data, sports)


if __name__ == "__main__":
    sys.exit(main())

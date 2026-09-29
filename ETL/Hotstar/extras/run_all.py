"""
run_all.py — run the OTT sports scrapers and produce one merged CSV.  (AUDITED)

Usage
-----
    python run_all.py                                   # all three, live
    python run_all.py --platforms sonyliv zee5          # subset
    python run_all.py --raw-sonyliv sonyliv_raw.jsonl --raw-zee5 zee5_raw.jsonl   # re-parse
    python run_all.py --sport cricket                   # filter merged CSV + summary
    python run_all.py --sports-only                     # drop rows with no detected sport
    python run_all.py --debug                           # log every JSON response
    python run_all.py --headless                        # hide the window (may be blocked)

Output
------
    hotstar_sports.csv / sonyliv_sports.csv / zee5_sports.csv / ott_sports_merged.csv

Exit code is 1 if no platform produced any rows.
NOTE: the Hotstar block depends on hotstar_catalog.py, which was NOT part of the audit.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import traceback

import pandas as pd

from catalog_base import BOOL_COLS, COMMON_COLUMNS, detect_sport, save


# ── Hotstar (UNVERIFIED — hotstar_catalog.py not supplied) ───────────────────

def run_hotstar(a) -> pd.DataFrame | None:
    try:
        import hotstar_catalog as hc
    except ImportError:
        print("  ✗ hotstar_catalog.py not found — skipping Hotstar.")
        return None
    from catalog_base import Browser

    rows: list[dict] = []
    seen: set = set()

    def on_json(url, data):
        m = re.search(r"pageName=([\w-]+)", url)
        page = m.group(1).title() if m else "Sports"
        for tray, items in hc.iter_trays(data):
            for it in items:
                row = hc.item_to_row(it, tray, page)
                if not row:
                    continue
                key = (row.get("content_id"), row.get("rail"), page)
                if key in seen:
                    continue
                seen.add(key)
                genres = [g for g in str(row.get("genre_tags") or "").split(",") if g.strip()]
                sport, src = detect_sport(genres, row.get("title"), row.get("rail"),
                                          page, None)
                rows.append({
                    "platform": "Hotstar",
                    "rail": row.get("rail"), "page": page,
                    "section": row.get("series_tag"),
                    "content_id": str(row.get("content_id", "")),
                    "title": row.get("title", ""),
                    "content_type": row.get("content_type", ""),
                    "is_live": None,                       # not provided → unknown (was hard-coded False)
                    "description": row.get("description", "") or "",
                    "year": row.get("year"), "rating": row.get("rating"),
                    "duration_label": row.get("duration"),
                    "sport": sport or row.get("series_tag"),
                    "sport_source": src or ("series_tag" if row.get("series_tag") else None),
                    "tournament": row.get("series_tag"),
                    "primary_genre": row.get("primary_genre"),
                    "genre_tags": row.get("genre_tags", ""),
                    "languages": row.get("languages", ""),
                    "original_language": row.get("original_language"),
                    "available_languages": row.get("available_languages", ""),
                    "language_count": row.get("language_count"),
                    # was hard-coded is_free=True ("Hotstar AVOD") — an assumption, not data
                    "is_free": None, "subscription_required": None, "pay_per_view": None,
                    "found_in": row.get("found_in", ""),
                    "detail_url": row.get("detail_url"),
                    "poster_url": row.get("poster_path"),
                })

    if a.raw_hotstar:
        print(f"  re-parsing {a.raw_hotstar} …")
        bad = 0
        with open(a.raw_hotstar, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    d = json.loads(line)
                    on_json(d["url"], d["data"])
                except Exception:                            # noqa: BLE001
                    bad += 1
        if bad:
            print(f"  ⚠  {bad} raw Hotstar records could not be parsed")
    else:
        b = Browser(on_json, raw_path="hotstar_raw.jsonl", append=not a.overwrite,
                    delay=a.delay, headed=not a.headless, headless_new=True, debug=a.debug)
        b.start()
        try:
            for slug in ["/in/sports", "/in/sports/cricket", "/in/sports/football",
                         "/in/sports/tennis", "/in/sports/kabaddi", "/in/sports/hockey",
                         "/in/sports/badminton", "/in/sports/motorsports"]:
                print(f"    {slug} …")
                b.current_page = slug
                b.visit(hc.BASE + slug, deep=True)
                print(f"    {len(rows)} rows")
        finally:
            b.close()
    return save(rows, "hotstar_sports.csv", COMMON_COLUMNS, platform="Hotstar")


# ── entry-point ──────────────────────────────────────────────────────────────

def _banner(name: str):
    print("\n" + "═" * 50 + f"\n  {name}\n" + "═" * 50)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--platforms", nargs="*", choices=["hotstar", "sonyliv", "zee5"],
                    default=["hotstar", "sonyliv", "zee5"])
    ap.add_argument("--raw-hotstar", help="Hotstar JSONL to re-parse")
    ap.add_argument("--raw-sonyliv", help="SonyLIV JSONL to re-parse")
    ap.add_argument("--raw-zee5", help="ZEE5 JSONL to re-parse")
    ap.add_argument("--sport", help="keep only rows matching this sport (merged CSV + summary)")
    ap.add_argument("--sports-only", action="store_true", help="drop rows with no detected sport")
    ap.add_argument("--out", default="ott_sports_merged.csv")
    ap.add_argument("--delay", type=float, default=1.5)
    ap.add_argument("--overwrite", action="store_true", help="overwrite raw JSONL instead of appending")
    ap.add_argument("--headless", action="store_true",
                    help="hide the browser window (some sites answer 403 to headless browsers)")
    ap.add_argument("--headed", action="store_true", help=argparse.SUPPRESS)   # kept for old commands
    ap.add_argument("--debug", action="store_true", help="log every JSON response + tracebacks")
    a = ap.parse_args()

    dfs: list[pd.DataFrame] = []
    empty: list[str] = []

    def collect(name: str, fn):
        _banner(name.upper())
        try:
            df = fn()
        except SystemExit:
            raise
        except Exception as e:                               # noqa: BLE001
            print(f"  ✗ {name} failed: {type(e).__name__}: {e}")
            if a.debug:
                traceback.print_exc()
            empty.append(name)
            return
        if df is None or df.empty:
            empty.append(name)
        else:
            dfs.append(df)

    if "hotstar" in a.platforms:
        collect("hotstar", lambda: run_hotstar(a))
    if "sonyliv" in a.platforms:
        import sonyliv_catalog as sl
        collect("sonyliv", lambda: sl.parse_file(a.raw_sonyliv, "sonyliv_sports.csv")
                if a.raw_sonyliv else
                sl.crawl(out="sonyliv_sports.csv", append=not a.overwrite, delay=a.delay,
                         headed=not a.headless, headless_new=True, debug=a.debug))
    if "zee5" in a.platforms:
        import zee5_catalog as z5
        collect("zee5", lambda: z5.parse_file(a.raw_zee5, "zee5_sports.csv")
                if a.raw_zee5 else
                z5.crawl(out="zee5_sports.csv", append=not a.overwrite, delay=a.delay,
                         headed=not a.headless, headless_new=True, debug=a.debug))

    if empty:
        print(f"\n  ⚠  No rows from: {', '.join(empty)}")
    if not dfs:
        print("No data collected.")
        return 1

    merged = pd.concat(dfs, ignore_index=True)
    if a.sports_only:
        merged = merged[merged["sport"].notna()]
    if a.sport:
        needle = re.escape(a.sport.lower())
        mask = pd.Series(False, index=merged.index)
        for col in ("sport", "genre_tags", "tournament"):
            mask |= merged[col].astype("string").str.lower().str.contains(needle, na=False)
        merged = merged[mask]
    merged.to_csv(a.out, index=False)
    print(f"\n  ✓ merged → {a.out}  ({len(merged)} rows)")

    print_summary(merged)
    return 0


def print_summary(df: pd.DataFrame):
    print("\n" + "═" * 60)
    print("  FULL SUMMARY — ALL PLATFORMS")
    print("═" * 60)
    if df.empty:
        print("\n  (no rows after filters)\n" + "═" * 60)
        return

    total = len(df)
    unique = len(df[["platform", "content_id"]].drop_duplicates())   # IDs are per-platform
    print(f"\n  Total rows  : {total}")
    print(f"  Unique titles (platform+ID): {unique}")

    print("\n  ── By Platform ──")
    for plat, grp in df.groupby("platform"):
        print(f"    {plat:<12} {len(grp):>5} rows  ({grp['content_id'].nunique()} unique)")

    print("\n  ── Content types ──")
    print(df.groupby(["platform", "content_type"]).size().unstack(fill_value=0).to_string())

    print("\n  ── Top sports ──")
    for sp, cnt in df["sport"].dropna().value_counts().head(15).items():
        plats = ", ".join(sorted(df.loc[df["sport"] == sp, "platform"].dropna().unique()))
        print(f"    {sp:<20} {cnt:>5}  [{plats}]")

    print("\n  ── Top tournaments ──")
    for t, cnt in df["tournament"].dropna().value_counts().head(10).items():
        print(f"    {str(t)[:45]:<45} {cnt:>5}")

    b = {c: df[c].astype("boolean") for c in BOOL_COLS}
    print("\n  ── Access model (rows) ──")
    print(f"    Free AVOD        : {int(b['is_free'].fillna(False).sum()):>5}")
    print(f"    Sub required     : {int(b['subscription_required'].fillna(False).sum()):>5}")
    print(f"    Pay-per-view     : {int(b['pay_per_view'].fillna(False).sum()):>5}")
    print(f"    Unknown access   : {int(b['is_free'].isna().sum()):>5}")

    print("\n  ── Live content ──")
    print(f"    Live rows   : {int(b['is_live'].fillna(False).sum()):>5}")

    print("\n  ── Missing data ──")
    for col in ["sport", "tournament", "description", "year", "rating", "is_free"]:
        if col in df.columns:
            blank = df[col].isna() | (df[col].astype("string").str.strip() == "")
            print(f"    {col:<20} missing: {int(blank.sum()):>5} ({blank.mean() * 100:.1f}%)")
    print("═" * 60 + "\n")


if __name__ == "__main__":
    sys.exit(main())

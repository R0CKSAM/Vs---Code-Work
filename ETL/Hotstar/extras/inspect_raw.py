"""
inspect_raw.py — v2: digs into resultObj / GraphQL data / nested containers.

Usage
-----
    python inspect_raw.py zee5_raw.jsonl
    python inspect_raw.py sonyliv_raw.jsonl --sample 2
    python inspect_raw.py sonyliv_raw.jsonl --only apiv3.sonyliv.com
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from urllib.parse import urlparse

# Windows consoles default to cp1252 and cannot encode box-drawing chars.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _endpoint(url: str) -> str:
    u = urlparse(url or "")
    return f"{u.hostname or '?'}{u.path or ''}"


# ── OLD behaviour (kept for test compatibility) ──────────────────────────────
def _find_item_list(data, _d: int = 0):
    """Return (jq-ish path, items) for the most likely item list at top / data.* level."""
    if _d > 4:
        return None, None
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return "$", data
    if isinstance(data, dict):
        for key in ("bucket_response", "buckets", "containers",
                    "response", "result", "items"):
            v = data.get(key)
            if isinstance(v, list) and v and isinstance(v[0], dict):
                first = v[0]
                if isinstance(first, dict) and any(k in first for k in ("items", "assets")):
                    flat = [it for b in v
                            for it in (b.get("items") or b.get("assets") or [])
                            if isinstance(it, dict)]
                    return f"$.{key}[].items", flat
                return f"$.{key}", v
        v = data.get("data")
        if isinstance(v, dict):
            return _find_item_list(v, _d + 1)
    return None, None


# ── NEW: recursive scan for content-like lists ──────────────────────────────
_ID_KEYS    = ("id", "contentId", "assetId", "content_id", "asset_id", "showId")
_TITLE_KEYS = ("title", "name", "episodeTitle", "showName", "assetTitle")


def _is_content_item(d) -> bool:
    if not isinstance(d, dict):
        return False
    return (any(k in d for k in _ID_KEYS)
            and any(k in d for k in _TITLE_KEYS))


def _find_content_lists(node, path: str = "$", _d: int = 0, _out=None):
    """Every list whose elements look like content items."""
    if _out is None:
        _out = []
    if _d > 9 or len(_out) >= 6:
        return _out
    if isinstance(node, dict):
        for k, v in node.items():
            _find_content_lists(v, f"{path}.{k}", _d + 1, _out)
    elif isinstance(node, list) and node:
        if any(_is_content_item(x) for x in node[:3]):
            _out.append((path, node))
            return _out
        for i, v in enumerate(node[:3]):
            _find_content_lists(v, f"{path}[{i}]", _d + 1, _out)
    return _out


def _row_count_for(platform, url, data):
    try:
        if platform == "zee5":
            import zee5_catalog as z5
            p = z5.ZEE5Parser()
        elif platform == "sonyliv":
            import sonyliv_catalog as sl
            p = sl.SonyLIVParser()
        else:
            return None
        p.parse(url, data)
        return len(p.rows)
    except Exception:
        return None


def _keys_of(items, n=25):
    c = Counter()
    for it in items[:20]:
        if isinstance(it, dict):
            for k in it:
                c[k] += 1
    return ", ".join(k for k, _ in c.most_common(n))


def inspect(raw_path: str, sample: int = 2, only: str | None = None):
    records = []
    with open(raw_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    by_ep = defaultdict(list)
    for r in records:
        by_ep[_endpoint(r.get("url", ""))].append(r)

    print(f"records: {len(records)}  endpoints: {len(by_ep)}\n")

    items_sorted = sorted(by_ep.items(), key=lambda x: -len(x[1]))
    if only:
        items_sorted = [(e, r) for e, r in items_sorted if only in e]

    for ep, recs in items_sorted:
        print(f"-- {ep}  ({len(recs)} records)")
        for u in list({r.get("url") for r in recs})[:2]:
            print(f"   url: {(u or '')[:130]}")

        platform = "zee5" if "zee5" in ep else ("sonyliv" if "sonyliv" in ep else None)

        # best row count over all records for this endpoint
        best_rows, best_data = 0, None
        for r in recs:
            n = _row_count_for(platform, r.get("url"), r.get("data"))
            if n and n > best_rows:
                best_rows, best_data = n, r.get("data")
        if best_data is None:
            best_data = recs[0].get("data")
        print(f"   rows_from_current_parser={best_rows}")

        d = best_data

        # ── old, shallow "item list" detection (test-compatible) ────────────
        path, items = _find_item_list(d)
        if path:
            print(f"   item list: {path}  ({len(items)} items in first record)")
            print(f"   item keys: {_keys_of(items)}")
            for it in items[:sample]:
                print(f"   sample: {json.dumps(it, ensure_ascii=False)[:400]}")
        else:
            print("   item list: (not detected)")
            if isinstance(d, dict):
                print(f"   top keys: {', '.join(list(d)[:20])}")

        # ── new, deep scan ──────────────────────────────────────────────────
        found = _find_content_lists(d)
        # Only show lists not already printed by the shallow scan
        extra = [(p, lst) for p, lst in found if p != path]
        if extra:
            print("   [deep scan] content-like lists found:")
            for p, lst in extra[:3]:
                print(f"      {p}  ({len(lst)} items)")
                print(f"         keys: {_keys_of(lst)}")
                for it in lst[:sample]:
                    print(f"         sample: {json.dumps(it, ensure_ascii=False)[:600]}")

        # If nothing found anywhere, at least show the wrappers
        if not found and isinstance(d, dict):
            for wrapper in ("resultObj", "data"):
                sub = d.get(wrapper)
                if isinstance(sub, dict):
                    print(f"   {wrapper} keys: {', '.join(list(sub)[:30])}")
                    # one level deeper for the two common GraphQL patterns
                    for k2, v2 in list(sub.items())[:5]:
                        if isinstance(v2, dict):
                            print(f"     {wrapper}.{k2} keys: {', '.join(list(v2)[:20])}")
        print()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("raw")
    ap.add_argument("--sample", type=int, default=2)
    ap.add_argument("--only", help="substring filter on endpoint")
    a = ap.parse_args()
    inspect(a.raw, a.sample, a.only)
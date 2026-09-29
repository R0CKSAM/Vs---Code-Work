"""dump.py — print the full JSON of the first N raw records matching a URL substring."""
import argparse, json, sys
for s in (sys.stdout, sys.stderr):
    try: s.reconfigure(encoding="utf-8")
    except Exception: pass

ap = argparse.ArgumentParser()
ap.add_argument("raw")
ap.add_argument("--match", required=True, help="substring of the URL")
ap.add_argument("--max", type=int, default=1, help="how many records to print")
ap.add_argument("--chars", type=int, default=8000, help="max chars per record")
a = ap.parse_args()

printed = 0
with open(a.raw, encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if not line: continue
        try: d = json.loads(line)
        except json.JSONDecodeError: continue
        if a.match not in d.get("url", ""): continue
        print("=" * 80)
        print("URL :", d.get("url"))
        print("PAGE:", d.get("page"))
        print("=" * 80)
        print(json.dumps(d.get("data"), indent=2, ensure_ascii=False)[:a.chars])
        print()
        printed += 1
        if printed >= a.max:
            break
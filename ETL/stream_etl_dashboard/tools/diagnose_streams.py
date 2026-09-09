"""Count configured stream path segments in the newest local gzip logs."""
from __future__ import annotations

import gzip
import json
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import unquote


root = Path(sys.argv[1])
limit = int(sys.argv[2]) if len(sys.argv) > 2 else 5000
targets = tuple(sys.argv[3:]) or ("vglive-274906", "vglive-sk-274906", "upgovlive")
files = sorted(root.rglob("*.gz"), key=lambda p: p.stat().st_mtime_ns, reverse=True)[:limit]
counts = Counter()
examples = {}
for path in files:
    try:
        with gzip.open(path, "rt", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                event = json.loads(line)
                request_path = unquote(event.get("reqPath") or event.get("reqUrl") or "")
                segments = request_path.split("?", 1)[0].strip("/").split("/")
                for target in targets:
                    if target in segments:
                        counts[target] += 1
                        examples.setdefault(target, request_path)
    except (OSError, json.JSONDecodeError):
        continue
print(f"Scanned {len(files)} files")
for target in targets:
    print(f"{target}: {counts[target]} records")
    if target in examples:
        print(f"  example: {examples[target]}")

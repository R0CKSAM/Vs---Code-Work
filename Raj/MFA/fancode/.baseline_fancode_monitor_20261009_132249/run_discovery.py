"""
run_discovery.py – Standalone discovery executor script for FanCode Monitor Phase 1.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.scraper.discovery.__main__ import main

if __name__ == "__main__":
    sys.exit(main())

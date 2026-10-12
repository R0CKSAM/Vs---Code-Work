"""
__main__.py – CLI entrypoint for database initialization.

Usage:
    python -m app.database
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is importable
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database.connection import init_db
from app.database.migrations import get_existing_tables, verify_schema


def main() -> int:
    print("\n===========================================================")
    print("   FanCode Monitor - Database Initialization (Phase 2)")
    print("===========================================================")
    init_db()
    tables = get_existing_tables()
    print(f"✅ Database initialized successfully. Found {len(tables)} tables:")
    for t in sorted(tables):
        print(f"   - {t}")
    verified = verify_schema()
    print(f"Schema verification: {'PASSED' if verified else 'FAILED'}\n")
    return 0 if verified else 1


if __name__ == "__main__":
    sys.exit(main())

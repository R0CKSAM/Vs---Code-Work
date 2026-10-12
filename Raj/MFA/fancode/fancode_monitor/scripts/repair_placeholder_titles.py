"""Repair generic match titles from canonical FanCode match URLs.

Dry-run is the default. ``--execute`` creates a timestamped database backup,
applies one transaction, and verifies SQLite integrity before committing.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database.backup import create_sqlite_backup

DEFAULT_DB = ROOT / "data" / "fancode.db"
PLACEHOLDER_RE = re.compile(r"^match[ -]?\d+$", re.IGNORECASE)
MATCH_SLUG_RE = re.compile(r"/matches/([^/?#]+?)-(\d+)(?:/|$)", re.IGNORECASE)


def derive_title_and_slug(source_url: str) -> tuple[str, str] | None:
    """Derive a team-vs-team title only from a specific canonical match URL."""
    match = MATCH_SLUG_RE.search(urlparse(source_url).path)
    if not match:
        return None
    slug = match.group(1).strip("-").lower()
    if "-vs-" not in slug and "-v-" not in slug:
        return None
    words = slug.replace("-vs-", " vs ").replace("-v-", " vs ").replace("-", " ")
    title = " ".join(word if word == "vs" else word.title() for word in words.split())
    return title, slug


def find_repairs(connection: sqlite3.Connection) -> list[tuple[str, str, int, str]]:
    repairs: list[tuple[str, str, int, str]] = []
    rows = connection.execute("SELECT id, title, source_url FROM matches ORDER BY id")
    for row_id, title, source_url in rows:
        if not title or not PLACEHOLDER_RE.fullmatch(title.strip()) or not source_url:
            continue
        derived = derive_title_and_slug(source_url)
        if derived:
            repairs.append((derived[0], derived[1], row_id, title))
    return repairs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DB)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    db_path = args.database.resolve()
    if not db_path.is_file():
        parser.error(f"database does not exist: {db_path}")

    connection = sqlite3.connect(db_path)
    try:
        repairs = find_repairs(connection)
        print(f"placeholder_title_repairs={len(repairs)}")
        for new_title, new_slug, row_id, old_title in repairs:
            print(f"  id={row_id}: {old_title!r} -> {new_title!r} ({new_slug})")
        if not args.execute:
            print("mode=DRY_RUN; database unchanged")
            return 0

        backup_dir = db_path.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"fancode_before_title_repair_{stamp}.db"
        create_sqlite_backup(db_path, backup_path)
        print(f"backup={backup_path}")

        connection.execute("BEGIN IMMEDIATE")
        for new_title, new_slug, row_id, old_title in repairs:
            connection.execute(
                "UPDATE matches SET title=?, slug=?, updated_at=CURRENT_TIMESTAMP WHERE id=? AND title=?",
                (new_title, new_slug, row_id, old_title),
            )
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"integrity_check failed: {integrity}")
        connection.commit()
        print(f"repaired={len(repairs)}; integrity_check=ok")
        return 0
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())

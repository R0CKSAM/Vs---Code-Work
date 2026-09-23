"""Reusable insight configurations; optional non-destructive account installation."""
import argparse
import json
from pathlib import Path
import sqlite3

INSIGHT_PRESETS = [
    {'id': 'insight-views', 'name': 'Daily views vs total revenue', 'config': {'type': 'mixed', 'group': 'day', 'first': 'views', 'second': 'total'}},
    {'id': 'insight-leader', 'name': 'Highest-revenue channel each day', 'config': {'type': 'bar', 'group': 'leader', 'first': 'total', 'second': 'none'}},
    {'id': 'insight-mix', 'name': 'Daily ad revenue vs sponsorship', 'config': {'type': 'grouped', 'group': 'day', 'first': 'ad', 'second': 'other'}},
    {'id': 'insight-share', 'name': 'Channel revenue share', 'config': {'type': 'pie', 'group': 'channel', 'first': 'total', 'second': 'none'}},
]


def install(database, username):
    # rw prevents accidentally creating a new database at a mistyped path.
    db = sqlite3.connect(Path(database).resolve().as_uri() + '?mode=rw', uri=True)
    try:
        with db:
            user = db.execute('SELECT id FROM users WHERE username=? COLLATE NOCASE', (username,)).fetchone()
            if not user:
                raise ValueError('Account not found; no changes made.')
            before = db.total_changes
            for preset in INSIGHT_PRESETS:
                db.execute('INSERT OR IGNORE INTO graph_presets(user_id,name,config) VALUES (?,?,?)',
                           (user[0], preset['name'], json.dumps(preset['config'])))
            return db.total_changes - before
    finally:
        db.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--username', required=True)
    args = parser.parse_args()
    print(f'Added {install(args.database, args.username)} presets; existing presets preserved.')

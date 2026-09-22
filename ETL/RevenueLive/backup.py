"""Take a consistent SQLite backup and preserve the original uploads."""
import datetime as dt
from pathlib import Path
import shutil
import sqlite3
from contextlib import closing

root=Path(__file__).resolve().parent
target=root/'backups'/dt.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
if not (root/'data/revenuelive.db').exists():
    raise SystemExit('No RevenueLive database found.')
target.mkdir(parents=True)
with closing(sqlite3.connect(root/'data/revenuelive.db')) as source, closing(sqlite3.connect(target/'revenuelive.db')) as dest:
    source.backup(dest)
shutil.copytree(root/'data/uploads',target/'uploads')
print('Backup:',target)

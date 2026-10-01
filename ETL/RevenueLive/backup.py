"""Take a consistent SQLite backup and preserve the original uploads."""
import os
from pathlib import Path
from app import backup_database

root=Path(__file__).resolve().parent
print('Backup:',backup_database(os.environ.get('REVENUE_DATA_DIR',root/'data')))

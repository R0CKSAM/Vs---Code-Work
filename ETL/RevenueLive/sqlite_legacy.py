"""Existing SQLite upgrade path, retained for local use and source migrations."""
import hashlib
import json


def initialize(db, audit_digest, verify_audit_chain, AUDIT_GENESIS):
    db().executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE COLLATE NOCASE, password TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','uploader','viewer')), active INTEGER NOT NULL DEFAULT 1, must_change INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS channels(id INTEGER PRIMARY KEY, name TEXT UNIQUE COLLATE NOCASE NOT NULL);
        CREATE TABLE IF NOT EXISTS channel_aliases(name TEXT PRIMARY KEY, channel_id INTEGER NOT NULL REFERENCES channels(id));
        CREATE TABLE IF NOT EXISTS channel_branding(channel_id INTEGER PRIMARY KEY REFERENCES channels(id), fallback_name TEXT NOT NULL, logo_base64 TEXT NOT NULL, logo_version TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS assignments(user_id INTEGER REFERENCES users(id), channel_id INTEGER REFERENCES channels(id), PRIMARY KEY(user_id,channel_id));
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id INTEGER REFERENCES users(id), csrf TEXT NOT NULL, expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS attempts(ip TEXT PRIMARY KEY, failures INTEGER, expires REAL);
        CREATE TABLE IF NOT EXISTS uploads(id TEXT PRIMARY KEY, user_id INTEGER REFERENCES users(id), filename TEXT, digest TEXT, created TEXT, state TEXT, rows_json TEXT, preview_json TEXT, archived INTEGER NOT NULL DEFAULT 0, file_deleted INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS records(day TEXT, channel_id INTEGER REFERENCES channels(id), views INTEGER, impressions INTEGER, ad INTEGER, other INTEGER, total INTEGER, upload_id TEXT, PRIMARY KEY(day,channel_id));
        CREATE TABLE IF NOT EXISTS revisions(upload_id TEXT, day TEXT, channel_id INTEGER, previous TEXT);
        CREATE INDEX IF NOT EXISTS idx_records_upload ON records(upload_id);
        CREATE INDEX IF NOT EXISTS idx_revisions_upload ON revisions(upload_id);
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, created TEXT, user_id INTEGER, action TEXT, detail TEXT, actor TEXT, prev_hash TEXT, entry_hash TEXT);
        CREATE TABLE IF NOT EXISTS super_admin(singleton INTEGER PRIMARY KEY CHECK(singleton=1), user_id INTEGER UNIQUE NOT NULL REFERENCES users(id));
        CREATE TABLE IF NOT EXISTS archived_channels(channel_id INTEGER PRIMARY KEY REFERENCES channels(id));
        CREATE TABLE IF NOT EXISTS hidden_dates(day TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS graph_presets(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), name TEXT NOT NULL COLLATE NOCASE, config TEXT NOT NULL, UNIQUE(user_id,name));
    ''')
    upload_columns={row['name'] for row in db().execute('PRAGMA table_info(uploads)')}
    for column in ('archived','file_deleted'):
        if column not in upload_columns:
            db().execute(f'ALTER TABLE uploads ADD COLUMN {column} INTEGER NOT NULL DEFAULT 0')
    audit_columns={row['name'] for row in db().execute('PRAGMA table_info(audit)')}
    for column in ('actor','prev_hash','entry_hash'):
        if column not in audit_columns:
            db().execute(f'ALTER TABLE audit ADD COLUMN {column} TEXT')
    legacy_audit=list(db().execute('SELECT * FROM audit ORDER BY id'))
    if legacy_audit and all(not row['entry_hash'] for row in legacy_audit):
        previous=AUDIT_GENESIS
        for row in legacy_audit:
            owner=db().execute('SELECT username FROM users WHERE id=?',(row['user_id'],)).fetchone()
            actor=owner['username'] if owner else f"User #{row['user_id']}"
            entry=dict(row);entry.update(actor=actor,prev_hash=previous)
            current_hash=audit_digest(entry)
            db().execute('UPDATE audit SET actor=?,prev_hash=?,entry_hash=? WHERE id=?',(actor,previous,current_hash,row['id']))
            previous=current_hash
    elif any(not row['entry_hash'] for row in legacy_audit):
        raise RuntimeError('Audit chain is incomplete; do not start until investigated.')
    db().executescript('''
        CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit BEGIN SELECT RAISE(ABORT,'Audit events cannot be edited'); END;
        CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit BEGIN SELECT RAISE(ABORT,'Audit events cannot be deleted'); END;
    ''')
    valid,_,_,broken=verify_audit_chain(db())
    if not valid:
        raise RuntimeError(f'Audit chain verification failed at event {broken}.')
    db().commit()

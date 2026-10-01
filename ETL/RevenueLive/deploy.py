"""Explicit MySQL provisioning and read-only SQLite migration commands."""
import argparse
from contextlib import closing
import datetime as dt
import getpass
import hashlib
import json
from pathlib import Path
import sqlite3

from alembic import command
from alembic.config import Config
from sqlalchemy import select, func, text
from werkzeug.security import generate_password_hash

from config import ROOT, Settings
from database import Database
from db_schema import metadata


def upgrade(database):
    configuration = Config()
    configuration.set_main_option('script_location', str(ROOT / 'migrations'))
    with database.engine.connect() as connection:
        lock_name = 'revenue-migrate-' + hashlib.sha256(database.settings.db_url.database.encode()).hexdigest()[:24]
        if connection.execute(text('SELECT GET_LOCK(:name, 30)'), {'name': lock_name}).scalar() != 1:
            raise RuntimeError('Another database migration is running.')
        connection.commit()
        try:
            configuration.attributes['connection'] = connection
            command.upgrade(configuration, 'head')
            connection.commit()
        finally:
            connection.execute(text('SELECT RELEASE_LOCK(:name)'), {'name': lock_name})
            connection.commit()


def import_sqlite(database, source_file, source_uploads=None):
    from app import verify_audit_chain
    database.check_schema()
    source_file = Path(source_file).resolve(strict=True)
    ephemeral = {'sessions', 'attempts', 'email_tokens', 'email_limits', 'write_lock'}
    tables = [table for table in metadata.sorted_tables if table.name not in ephemeral]
    # Legacy source_uploads is accepted for old deployment commands, but unused.
    with closing(sqlite3.connect(source_file.as_uri() + '?mode=ro', uri=True)) as source:
        source.row_factory = sqlite3.Row
        source.execute('BEGIN')
        valid, _, _, broken = verify_audit_chain(source)
        if not valid:
            raise ValueError(f'Source audit history is invalid at event {broken}.')
        with database.engine.begin() as target:
            target.execute(select(metadata.tables['write_lock']).with_for_update()).first()
            for table in metadata.sorted_tables:
                if table.name != 'write_lock' and target.execute(select(func.count()).select_from(table)).scalar():
                    raise ValueError('Import requires an empty migrated database, before creating the admin account.')
            for table in tables:
                cursor = source.execute(f'SELECT * FROM "{table.name}"')
                if set(column[0] for column in cursor.description) != set(table.c.keys()):
                    raise ValueError(f'Source schema for {table.name} is outdated; upgrade a SQLite copy first.')
                count = 0
                while rows := cursor.fetchmany(500):
                    target.execute(table.insert(), [dict(row) for row in rows])
                    count += len(rows)
                if target.execute(select(func.count()).select_from(table)).scalar() != count:
                    raise RuntimeError(f'Row count mismatch for {table.name}.')
            for metric in ('views', 'impressions', 'ad', 'other', 'total'):
                before = source.execute(f'SELECT COALESCE(SUM({metric}),0) FROM records').fetchone()[0]
                after = target.execute(select(func.coalesce(func.sum(metadata.tables['records'].c[metric]), 0))).scalar()
                if before != after:
                    raise RuntimeError(f'Migration total mismatch: {metric}.')
            # Preserve the exact audit payload and hash chain, including original IDs.
            for row in source.execute('SELECT * FROM audit ORDER BY id'):
                imported = target.execute(select(metadata.tables['audit']).where(metadata.tables['audit'].c.id == row['id'])).mappings().one()
                if dict(imported) != dict(row):
                    raise RuntimeError('Audit payload changed during migration.')


def init_admin(database, username, password):
    if not username or len(username) > 80 or not 12 <= len(password) <= 256:
        raise ValueError('Use a username up to 80 characters and a password of 12 to 256 characters.')
    database.check_schema()
    with closing(database.connect()) as connection, connection:
        connection.begin_write()
        if connection.execute('SELECT 1 FROM users LIMIT 1').fetchone():
            raise ValueError('Users already exist. Initial admin creation is only for a fresh installation.')
        uid = connection.execute("INSERT INTO users(username,password,role,must_change) VALUES (?,?,'admin',1)",
                                 (username, generate_password_hash(password))).lastrowid
        connection.execute('INSERT INTO super_admin VALUES (1,?)', (uid,))


def reset_super_admin(database, username, password):
    """Assign ownership, reset its password, revoke sessions, and append audit."""
    from app import AUDIT_GENESIS, audit_digest, verify_audit_chain
    if not username or len(username) > 80 or not 12 <= len(password) <= 256:
        raise ValueError('Use a username up to 80 characters and a password of 12 to 256 characters.')
    database.check_schema()
    with closing(database.connect()) as connection, connection:
        connection.begin_write()
        valid, _, _, broken = verify_audit_chain(connection)
        if not valid:
            raise RuntimeError(f'Audit chain verification failed at event {broken}.')
        previous = connection.execute(
            'SELECT u.username FROM super_admin s JOIN users u ON u.id=s.user_id WHERE s.singleton=1'
        ).fetchone()
        user = connection.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone()
        hashed = generate_password_hash(password)
        if user:
            uid = user['id']
            connection.execute("UPDATE users SET password=?,role='admin',active=1,must_change=1 WHERE id=?",
                               (hashed, uid))
        else:
            uid = connection.execute(
                "INSERT INTO users(username,password,role,active,must_change) VALUES (?,?,'admin',1,1)",
                (username, hashed)).lastrowid
        connection.upsert('super_admin', {'singleton':1, 'user_id':uid})
        connection.execute('DELETE FROM sessions WHERE user_id=?', (uid,))
        last = connection.execute('SELECT id,entry_hash FROM audit ORDER BY id DESC LIMIT 1').fetchone()
        event = dict(id=last['id']+1 if last else 1,
                     created=dt.datetime.now(dt.timezone.utc).isoformat(), user_id=uid,
                     actor='host-maintenance', action='super_admin_reset',
                     detail=json.dumps({'username':username,
                                        'previous_super_admin':previous['username'] if previous else None},
                                       separators=(',',':')),
                     prev_hash=last['entry_hash'] if last else AUDIT_GENESIS)
        event['entry_hash'] = audit_digest(event)
        connection.execute(
            'INSERT INTO audit(id,created,user_id,action,detail,actor,prev_hash,entry_hash) '
            'VALUES (:id,:created,:user_id,:action,:detail,:actor,:prev_hash,:entry_hash)', event)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    commands.add_parser('upgrade')
    commands.add_parser('check')
    admin = commands.add_parser('init-admin')
    admin.add_argument('--username', default='admin')
    recovery = commands.add_parser('super-admin', help='Set or recover the Super Admin account.')
    recovery.add_argument('--username', required=True)
    migrate = commands.add_parser('import-sqlite')
    migrate.add_argument('--source', required=True)
    migrate.add_argument('--source-uploads', help='Deprecated; upload rows are migrated from the database.')
    args = parser.parse_args()
    settings = Settings.from_env()
    database = Database(settings)
    if not database.mysql:
        parser.error('These commands require DB_DRIVER=mysql+pymysql or mariadb+pymysql.')
    try:
        if args.action == 'upgrade':
            upgrade(database)
        elif args.action == 'init-admin':
            password = getpass.getpass('Initial admin password: ')
            if password != getpass.getpass('Confirm password: '):
                raise ValueError('Passwords do not match.')
            init_admin(database, args.username, password)
        elif args.action == 'super-admin':
            password = getpass.getpass('New Super Admin password: ')
            if password != getpass.getpass('Confirm password: '):
                raise ValueError('Passwords do not match.')
            reset_super_admin(database, args.username, password)
        elif args.action == 'import-sqlite':
            import_sqlite(database, args.source, args.source_uploads)
        else:
            database.check_schema()
        print(f'{args.action}: complete')
    finally:
        database.engine.dispose()


if __name__ == '__main__':
    main()

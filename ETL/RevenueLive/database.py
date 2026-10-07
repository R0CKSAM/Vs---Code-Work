"""Database boundary for existing reporting queries and structured upserts."""
import os
import sqlite3

from sqlalchemy import create_engine, text, select
from sqlalchemy.dialects import mysql, sqlite
from sqlalchemy.exc import IntegrityError as SQLIntegrityError
from db_schema import metadata

INTEGRITY_ERRORS = (sqlite3.IntegrityError, SQLIntegrityError)
SCHEMA_REVISION = '0004_channel_merges'


def upsert_statement(dialect, name, values, ignore=False):
    target = metadata.tables[name]
    insert = (mysql.insert if dialect == 'mysql' else sqlite.insert)(target).values(**values)
    primary = list(target.primary_key.columns)
    updates = {key: (insert.inserted[key] if dialect == 'mysql' else insert.excluded[key])
               for key in values if key not in target.primary_key.columns}
    if dialect == 'mysql':
        # A no-op duplicate update avoids INSERT IGNORE suppressing unrelated errors.
        return insert.on_duplicate_key_update({primary[0].name: target.c[primary[0].name]} if ignore else updates)
    if ignore:
        return insert.on_conflict_do_nothing(index_elements=primary)
    return insert.on_conflict_do_update(index_elements=primary, set_=updates)


class SQLiteConnection(sqlite3.Connection):
    def begin_write(self):
        if not self.in_transaction:
            self.execute('BEGIN IMMEDIATE')

    def upsert(self, name, values, ignore=False):
        compiled = upsert_statement('sqlite', name, values, ignore).compile(dialect=sqlite.dialect())
        return self.execute(str(compiled), tuple(compiled.params[key] for key in compiled.positiontup))


class Row(dict):
    def __getitem__(self, key):
        return tuple(self.values())[key] if isinstance(key, int) else super().__getitem__(key)


class Result:
    def __init__(self, result):
        self.result = result
        self.lastrowid = result.lastrowid
        self.rowcount = result.rowcount

    def fetchone(self):
        row = self.result.fetchone()
        return Row(row._mapping) if row is not None else None

    def fetchall(self):
        return [Row(row._mapping) for row in self.result.fetchall()]

    def __iter__(self):
        return iter(self.fetchall())


class MySQLConnection:
    def __init__(self, engine):
        self.connection = engine.connect()
        self.locked = False

    def begin_write(self):
        if not self.locked:
            lock = metadata.tables['write_lock']
            if self.connection.execute(select(lock.c.id).where(lock.c.id == 1).with_for_update()).scalar_one_or_none() != 1:
                raise RuntimeError('Database write lock is missing. Run database migrations.')
            self.locked = True

    def execute(self, sql, parameters=()):
        # The existing static query templates use positional qmark parameters.
        # Only bind markers are adapted; values always remain driver parameters.
        if isinstance(parameters, dict):
            statement, bindings = sql, parameters
        else:
            parts = sql.split('?')
            if len(parts) != len(parameters) + 1:
                raise ValueError('SQL bind parameter count does not match.')
            statement = parts[0] + ''.join(f':p{i}' + part for i, part in enumerate(parts[1:]))
            bindings = {f'p{i}': value for i, value in enumerate(parameters)}
        if not sql.lstrip().upper().startswith('SELECT'):
            self.begin_write()
        return Result(self.connection.execute(text(statement), bindings))

    def executemany(self, sql, rows):
        for row in rows:
            self.execute(sql, row)

    def upsert(self, name, values, ignore=False):
        self.begin_write()
        return Result(self.connection.execute(upsert_statement('mysql', name, values, ignore)))

    def commit(self):
        self.connection.commit()
        self.locked = False

    def rollback(self):
        self.connection.rollback()
        self.locked = False

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, kind, value, traceback):
        self.rollback() if kind else self.commit()


class Database:
    def __init__(self, settings):
        self.settings = settings
        self.mysql = settings.db_url.get_backend_name() in {'mysql', 'mariadb'}
        self.engine = None
        if self.mysql:
            options = {'connect_timeout': 10}
            if os.environ.get('DB_SSL_CA'):
                options.update(ssl_ca=os.environ['DB_SSL_CA'], ssl_verify_cert=True, ssl_verify_identity=True)
            self.engine = create_engine(settings.db_url, pool_pre_ping=True, pool_recycle=1800,
                                        isolation_level='READ COMMITTED', connect_args=options)

    def connect(self):
        if self.mysql:
            return MySQLConnection(self.engine)
        connection = sqlite3.connect(self.settings.db_url.database, timeout=30, factory=SQLiteConnection)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        return connection

    def check_schema(self):
        with self.engine.connect() as connection:
            version = connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
            if version != SCHEMA_REVISION:
                raise RuntimeError('Database schema does not match this release. Run python deploy.py upgrade.')

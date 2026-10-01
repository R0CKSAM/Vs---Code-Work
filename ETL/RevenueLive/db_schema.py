"""Initial relational schema, shared with the first MySQL migration."""
from sqlalchemy import (MetaData, Table, Column, Integer, BigInteger, String, Float,
                        ForeignKey, UniqueConstraint, CheckConstraint, Index)
from sqlalchemy.dialects.mysql import LONGTEXT

metadata = MetaData()


def table(name, *columns):
    return Table(name, metadata, *columns, mysql_engine='InnoDB',
                 mysql_charset='utf8mb4', mysql_collate='utf8mb4_bin')


def col(name, kind, **kwargs):
    return Column(name, kind, **kwargs)


def identifier(name='id'):
    return col(name, Integer, primary_key=True, autoincrement=True)


def ref(name, target='users.id', primary=False):
    return Column(name, Integer, ForeignKey(target), primary_key=primary,
                  autoincrement=False, nullable=False)


def flag(name, default='0'):
    return col(name, Integer, nullable=False, server_default=default)


# Case-insensitive, accent-sensitive names; migration rejects any new collisions.
def identity_key(name, size):
    return col(name, String(size, collation='utf8mb4_unicode_ci'), nullable=False)


table('users', identifier(), identity_key('username', 100), col('password', String(512), nullable=False),
      col('role', String(16), nullable=False), flag('active', '1'), flag('must_change'),
      UniqueConstraint('username'), CheckConstraint("role IN ('admin','uploader','viewer')"))
table('channels', identifier(), identity_key('name', 120), UniqueConstraint('name'))
table('assignments', ref('user_id', primary=True), ref('channel_id', 'channels.id', True))
table('sessions', col('token', String(64), primary_key=True), ref('user_id'),
      col('csrf', String(64), nullable=False), col('expires', Float(53), nullable=False))
table('attempts', col('ip', String(64), primary_key=True), col('failures', Integer), col('expires', Float(53)))
table('uploads', col('id', String(64), primary_key=True), ref('user_id'), col('filename', String(255)),
      col('digest', String(64)), col('created', String(40)), col('state', String(20)),
      col('rows_json', LONGTEXT), col('preview_json', LONGTEXT), flag('archived'), flag('file_deleted'))
table('records', col('day', String(10), primary_key=True), ref('channel_id', 'channels.id', True),
      *(col(name, BigInteger) for name in ('views', 'impressions', 'ad', 'other', 'total')),
      col('upload_id', String(64)))
table('revisions', col('upload_id', String(64)), col('day', String(10)), col('channel_id', Integer),
      col('previous', LONGTEXT))
table('audit', col('id', BigInteger, primary_key=True, autoincrement=False), col('created', String(40)),
      col('user_id', Integer), col('action', String(80)), col('detail', LONGTEXT),
      col('actor', String(100)), col('prev_hash', String(64)), col('entry_hash', String(64)))
table('super_admin', col('singleton', Integer, primary_key=True, autoincrement=False), ref('user_id'),
      UniqueConstraint('user_id'), CheckConstraint('singleton=1'))
table('archived_channels', ref('channel_id', 'channels.id', True))
table('hidden_dates', col('day', String(10), primary_key=True), ref('user_id'), col('created', String(40), nullable=False))
table('graph_presets', identifier(), ref('user_id'), identity_key('name', 100),
      col('config', LONGTEXT, nullable=False), UniqueConstraint('user_id', 'name'))
table('email_accounts', ref('user_id', primary=True), identity_key('email', 100), flag('verified'), UniqueConstraint('email'))
table('email_tokens', col('token', String(64), primary_key=True), ref('user_id'), col('expires', Float(53), nullable=False))
table('email_limits', col('key', String(160), primary_key=True), col('expires', Float(53), nullable=False))
table('write_lock', col('id', Integer, primary_key=True, autoincrement=False))
Index('idx_records_upload', metadata.tables['records'].c.upload_id)
Index('idx_revisions_upload', metadata.tables['revisions'].c.upload_id)

"""Initial MySQL schema; legacy SQLite data is imported separately."""
from alembic import op
from db_schema import metadata

revision = '0001_mysql'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    metadata.create_all(connection)
    connection.execute(metadata.tables['write_lock'].insert().values(id=1))
    for action in ('UPDATE', 'DELETE'):
        op.execute(f"CREATE TRIGGER audit_no_{action.lower()} BEFORE {action} ON audit "
                   "FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Audit events cannot be edited or deleted'")


def downgrade():
    raise RuntimeError('Restore a verified backup instead of dropping production data.')

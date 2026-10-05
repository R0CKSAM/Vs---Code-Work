"""Channel rename aliases and database-backed logos."""
from alembic import op
from db_schema import metadata

revision = '0002_channel_branding'
down_revision = '0001_mysql'
branch_labels = None
depends_on = None


def upgrade():
    for name in ('channel_aliases', 'channel_branding'):
        metadata.tables[name].create(op.get_bind(), checkfirst=True)


def downgrade():
    raise RuntimeError('Restore a verified backup instead of dropping channel branding.')

"""Reversible channel reporting merges, preserving source ownership."""
from alembic import op
from db_schema import metadata

revision = '0004_channel_merges'
down_revision = '0003_user_profiles'
branch_labels = None
depends_on = None


def upgrade():
    metadata.tables['channel_merges'].create(op.get_bind(), checkfirst=True)


def downgrade():
    raise RuntimeError('Undo merges in the application instead of dropping their history.')

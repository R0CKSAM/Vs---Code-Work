"""Optional company names for user profiles."""
from alembic import op
from db_schema import metadata

revision = '0003_user_profiles'
down_revision = '0002_channel_branding'
branch_labels = None
depends_on = None


def upgrade():
    metadata.tables['user_profiles'].create(op.get_bind(), checkfirst=True)


def downgrade():
    raise RuntimeError('Restore a verified backup instead of dropping user profiles.')

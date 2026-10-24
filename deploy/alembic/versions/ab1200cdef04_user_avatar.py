"""Store normalized user avatars alongside account profiles."""
import sqlalchemy as sa
from alembic import op

revision = 'ab1200cdef04'
down_revision = 'ab1200cdef03'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('avatar_data', sa.Text(), nullable=False, server_default=''))


def downgrade():
    op.drop_column('users', 'avatar_data')

"""Track connection identity in LLM usage."""
import sqlalchemy as sa
from alembic import op

revision = 'ab1200cdef01'
down_revision = '22b15af22754'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('llm_usage', sa.Column('connection_id', sa.String(64), nullable=False, server_default=''))
    op.add_column('llm_usage', sa.Column('connection_name', sa.String(80), nullable=False, server_default=''))


def downgrade():
    op.drop_column('llm_usage', 'connection_name')
    op.drop_column('llm_usage', 'connection_id')

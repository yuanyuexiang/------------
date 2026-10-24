"""Link LLM calls to generation and parsing tasks."""
import sqlalchemy as sa
from alembic import op

revision = 'ab1200cdef02'
down_revision = 'ab1200cdef01'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('llm_usage', sa.Column('project_id', sa.String(12), nullable=False, server_default=''))
    op.add_column('llm_usage', sa.Column('task_id', sa.String(12), nullable=False, server_default=''))


def downgrade():
    op.drop_column('llm_usage', 'task_id')
    op.drop_column('llm_usage', 'project_id')

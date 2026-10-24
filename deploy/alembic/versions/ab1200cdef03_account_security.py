"""Account session revocation, audit and shared authentication throttles."""
import sqlalchemy as sa
from alembic import op

revision = 'ab1200cdef03'
down_revision = 'ab1200cdef02'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('session_version', sa.Integer(), nullable=False, server_default='0'))
    op.create_table('account_audit',
        sa.Column('id', sa.String(12), primary_key=True),
        sa.Column('actor', sa.String(64), nullable=False),
        sa.Column('target_id', sa.String(12), nullable=False),
        sa.Column('target_name', sa.String(64), nullable=False),
        sa.Column('action', sa.String(32), nullable=False),
        sa.Column('ok', sa.Boolean(), nullable=False),
        sa.Column('detail', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False))
    for column in ('target_id', 'action', 'created_at'):
        op.create_index('ix_account_audit_' + column, 'account_audit', [column])
    op.create_table('auth_throttle',
        sa.Column('key', sa.String(64), primary_key=True),
        sa.Column('failures', sa.Integer(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False))


def downgrade():
    op.drop_table('auth_throttle')
    op.drop_table('account_audit')
    op.drop_column('users', 'session_version')

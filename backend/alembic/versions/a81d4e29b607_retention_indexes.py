"""Indexes for age-based retention cleanup."""
from alembic import op

revision = 'a81d4e29b607'
down_revision = 'f7a10d92c630'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index('ix_monitor_checks_checked_at', 'monitor_checks', ['checked_at'])
    op.create_index('ix_notification_deliveries_created_at', 'notification_deliveries', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_notification_deliveries_created_at', table_name='notification_deliveries')
    op.drop_index('ix_monitor_checks_checked_at', table_name='monitor_checks')

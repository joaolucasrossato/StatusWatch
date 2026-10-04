"""create monitor_checks table"""
from alembic import op
import sqlalchemy as sa

revision = "b7c4e920d631"
down_revision = "9d2f3a7c8b10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "monitor_checks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("monitor_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(4), nullable=False),
        sa.Column("http_status_code", sa.Integer(), nullable=True),
        sa.Column("response_time_ms", sa.Integer(), nullable=True),
        sa.Column("error_type", sa.String(40), nullable=True),
        sa.Column("error_message", sa.String(200), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["monitor_id"], ["monitors.id"], ondelete="CASCADE"),
        sa.CheckConstraint("status IN ('UP', 'DOWN')", name="ck_monitor_checks_status"),
        sa.CheckConstraint("response_time_ms >= 0", name="ck_monitor_checks_response_time"),
    )
    op.create_index("ix_monitor_checks_monitor_id_checked_at", "monitor_checks", ["monitor_id", "checked_at"])


def downgrade() -> None:
    op.drop_index("ix_monitor_checks_monitor_id_checked_at", table_name="monitor_checks")
    op.drop_table("monitor_checks")

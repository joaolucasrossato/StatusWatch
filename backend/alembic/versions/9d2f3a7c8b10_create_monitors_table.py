"""create monitors table

Revision ID: 9d2f3a7c8b10
Revises: 4bffcd0e1da1
"""
from alembic import op
import sqlalchemy as sa

revision = "9d2f3a7c8b10"
down_revision = "4bffcd0e1da1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "monitors",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("url", sa.String(2083), nullable=False),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("interval_seconds", sa.Integer(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.CheckConstraint("interval_seconds > 0", name="ck_monitors_interval_positive"),
        sa.CheckConstraint("timeout_seconds > 0", name="ck_monitors_timeout_positive"),
    )
    op.create_index("ix_monitors_user_id", "monitors", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_monitors_user_id", table_name="monitors")
    op.drop_table("monitors")

"""Persistent notification channels and outbox.

Revision ID: f7a10d92c630
Revises: ec2cf41a52d5
"""
from alembic import op
import sqlalchemy as sa

revision = 'f7a10d92c630'
down_revision = 'ec2cf41a52d5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('notification_channels',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('user_id', sa.UUID(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('monitor_id', sa.UUID(), sa.ForeignKey('monitors.id', ondelete='CASCADE'), nullable=False),
        sa.Column('type', sa.String(7), nullable=False),
        sa.Column('target', sa.String(2083), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('notify_on_open', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('notify_on_resolved', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("type IN ('EMAIL', 'WEBHOOK')", name='ck_notification_channels_type'),
    )
    op.create_index('ix_notification_channels_user_monitor', 'notification_channels', ['user_id', 'monitor_id'])
    op.create_table('notification_deliveries',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('incident_id', sa.UUID(), sa.ForeignKey('incidents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('channel_id', sa.UUID(), sa.ForeignKey('notification_channels.id', ondelete='CASCADE'), nullable=False),
        sa.Column('event_type', sa.String(20), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(10), server_default='PENDING', nullable=False),
        sa.Column('attempt_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('last_error', sa.String(100)),
        sa.Column('claim_token', sa.UUID()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True)),
        sa.Column('next_attempt_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('incident_id', 'channel_id', 'event_type', name='uq_notification_delivery_transition'),
        sa.CheckConstraint("event_type IN ('INCIDENT_OPENED', 'INCIDENT_RESOLVED')", name='ck_notification_deliveries_event'),
        sa.CheckConstraint("status IN ('PENDING', 'PROCESSING', 'SENT', 'FAILED')", name='ck_notification_deliveries_status'),
        sa.CheckConstraint('attempt_count BETWEEN 0 AND 3', name='ck_notification_deliveries_attempts'),
    )
    op.create_index('ix_notification_deliveries_due', 'notification_deliveries', ['status', 'next_attempt_at'])
    op.create_index('ix_notification_deliveries_incident_created', 'notification_deliveries', ['incident_id', 'created_at'])
    op.create_index('ix_notification_deliveries_channel', 'notification_deliveries', ['channel_id'])


def downgrade() -> None:
    op.drop_table('notification_deliveries')
    op.drop_table('notification_channels')

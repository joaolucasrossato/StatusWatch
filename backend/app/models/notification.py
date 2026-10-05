import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class NotificationChannel(Base):
    __tablename__ = "notification_channels"
    __table_args__ = (
        CheckConstraint("type IN ('EMAIL', 'WEBHOOK')", name="ck_notification_channels_type"),
        Index("ix_notification_channels_user_monitor", "user_id", "monitor_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    monitor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("monitors.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(7))
    target: Mapped[str] = mapped_column(String(2083))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    notify_on_open: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    notify_on_resolved: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"
    __table_args__ = (
        UniqueConstraint("incident_id", "channel_id", "event_type", name="uq_notification_delivery_transition"),
        CheckConstraint("event_type IN ('INCIDENT_OPENED', 'INCIDENT_RESOLVED')", name="ck_notification_deliveries_event"),
        CheckConstraint("status IN ('PENDING', 'PROCESSING', 'SENT', 'FAILED')", name="ck_notification_deliveries_status"),
        CheckConstraint("attempt_count BETWEEN 0 AND 3", name="ck_notification_deliveries_attempts"),
        Index("ix_notification_deliveries_due", "status", "next_attempt_at"),
        Index("ix_notification_deliveries_incident_created", "incident_id", "created_at"),
        Index("ix_notification_deliveries_channel", "channel_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"))
    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("notification_channels.id", ondelete="CASCADE"))
    event_type: Mapped[str] = mapped_column(String(20))
    # Immutable transition snapshot; never returned by the deliveries API.
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(10), default="PENDING", server_default="PENDING")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_error: Mapped[str | None] = mapped_column(String(100))
    claim_token: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

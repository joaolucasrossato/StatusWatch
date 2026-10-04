import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.monitor import Monitor


class MonitorCheck(Base):
    __tablename__ = "monitor_checks"
    __table_args__ = (
        CheckConstraint("status IN ('UP', 'DOWN')", name="ck_monitor_checks_status"),
        CheckConstraint("response_time_ms >= 0", name="ck_monitor_checks_response_time"),
        Index("ix_monitor_checks_monitor_id_checked_at", "monitor_id", "checked_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    monitor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("monitors.id", ondelete="CASCADE"), nullable=False,
    )
    status: Mapped[str] = mapped_column(String(4), nullable=False)
    http_status_code: Mapped[int | None] = mapped_column(Integer)
    response_time_ms: Mapped[int | None] = mapped_column(Integer)
    error_type: Mapped[str | None] = mapped_column(String(40))
    error_message: Mapped[str | None] = mapped_column(String(200))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    monitor: Mapped["Monitor"] = relationship(back_populates="checks")

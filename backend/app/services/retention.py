"""Hourly retention; only terminal deliveries are eligible for deletion."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete

from app.core.config import Settings
from app.models import MonitorCheck, NotificationDelivery
from app.monitoring.scheduler import SessionFactory

logger = logging.getLogger(__name__)
CLEANUP_INTERVAL_SECONDS = 3600


def cleanup(sessions: SessionFactory, settings: Settings, now: datetime) -> tuple[int, int]:
    with sessions() as db, db.begin():
        checks = db.execute(delete(MonitorCheck).where(
            MonitorCheck.checked_at < now - timedelta(days=settings.check_retention_days),
        )).rowcount
        deliveries = db.execute(delete(NotificationDelivery).where(
            NotificationDelivery.created_at < now - timedelta(days=settings.notification_retention_days),
            NotificationDelivery.status.in_(['SENT', 'FAILED']),
        )).rowcount
    logger.info('cleanup_completed checks_deleted=%s deliveries_deleted=%s', checks, deliveries)
    return checks, deliveries


async def cleanup_loop(sessions: SessionFactory, settings: Settings, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await asyncio.to_thread(cleanup, sessions, settings, datetime.now(timezone.utc))
        except Exception as exc:
            logger.error('cleanup_failed class=%s', type(exc).__name__)
        try:
            await asyncio.wait_for(stop.wait(), timeout=CLEANUP_INTERVAL_SECONDS)
        except TimeoutError:
            continue

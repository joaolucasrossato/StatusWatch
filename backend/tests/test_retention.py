import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.core.config import Settings
from app.models import Incident, MonitorCheck, NotificationDelivery
from app.services.retention import cleanup, cleanup_loop
from test_notification_outbox import outbox, open_incident, rows


@pytest.mark.parametrize('status,deleted', [('SENT', 1), ('FAILED', 1), ('PENDING', 0), ('PROCESSING', 0)])
def test_cleanup_preserves_incidents_and_unfinished_deliveries(outbox, db, status, deleted):
    sessions, job, _ = outbox
    open_incident(sessions, job)
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=31)
    delivery = rows(db)[0]
    checks = list(db.scalars(select(MonitorCheck).order_by(MonitorCheck.checked_at)))
    checks[0].checked_at = old
    checks[1].checked_at = now - timedelta(days=30)  # Exact boundary is retained.
    delivery.created_at = old
    delivery.status = status
    db.commit()
    assert cleanup(sessions, Settings(), now) == (1, deleted)
    db.expire_all()
    assert len(list(db.scalars(select(MonitorCheck)))) == 2
    assert db.scalar(select(Incident.status)) == 'OPEN'
    assert len(rows(db)) == 1 - deleted
    assert cleanup(sessions, Settings(), now) == (0, 0)


def test_cleanup_respects_configured_windows(outbox, db):
    sessions, job, _ = outbox
    open_incident(sessions, job)
    now = datetime.now(timezone.utc)
    delivery = rows(db)[0]
    delivery.created_at = now - timedelta(days=4)
    delivery.status = 'SENT'
    db.commit()
    assert cleanup(sessions, Settings(check_retention_days=2, notification_retention_days=3), now) == (0, 1)


def test_cleanup_failure_waits_an_hour_and_recovers(caplog):
    async def run():
        stop = asyncio.Event()
        waits = []
        async def wait(awaitable, timeout):
            awaitable.close()
            waits.append(timeout)
            if len(waits) == 2:
                stop.set()
            raise TimeoutError
        with patch('app.services.retention.cleanup', side_effect=[RuntimeError('private'), (0, 0)]) as clean, \
             patch('app.services.retention.asyncio.wait_for', side_effect=wait):
            await cleanup_loop(None, Settings(), stop)
            assert clean.call_count == 2
            assert waits == [3600, 3600]
    asyncio.run(run())
    assert 'cleanup_failed' in caplog.text
    assert 'private' not in caplog.text


@pytest.mark.parametrize('field,value', [('check_retention_days', 0), ('notification_retention_days', -1),
                                        ('jwt_secret', ''), ('jwt_algorithm', 'none'), ('access_token_expire_minutes', 0)])
def test_invalid_retention_and_auth_config(field, value):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Settings(**{field: value})


def test_cleanup_rolls_back_both_deletes(outbox, db):
    from sqlalchemy import event
    sessions, job, _ = outbox
    open_incident(sessions, job)
    now = datetime.now(timezone.utc)
    for check in db.scalars(select(MonitorCheck)):
        check.checked_at = now - timedelta(days=31)
    db.commit()
    def fail(connection, cursor, statement, parameters, context, many):
        if statement.startswith('DELETE FROM notification_deliveries'):
            raise RuntimeError('database unavailable')
    event.listen(db.bind, 'before_cursor_execute', fail)
    try:
        with pytest.raises(RuntimeError):
            cleanup(sessions, Settings(), now)
    finally:
        event.remove(db.bind, 'before_cursor_execute', fail)
    assert len(list(db.scalars(select(MonitorCheck)))) == 3

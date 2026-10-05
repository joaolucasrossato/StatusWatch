"""PostgreSQL smoke in an automatically removed temporary DB; no external sends.

Run in the API image with this file mounted under /tmp. Requires CREATEDB.
"""
import asyncio
import os
import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from psycopg import sql
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, '/app')
from app.core.config import Settings
from app.models import Incident, Monitor, MonitorCheck, NotificationChannel, NotificationDelivery, User
from app.monitoring.checker import CheckResult, create_client
from app.monitoring.scheduler import MonitorJob, persist_check
from app.notifications.worker import claim_one, finish, run_delivery_cycle


def verify(engine) -> None:
    sessions = sessionmaker(bind=engine)
    with sessions() as db, db.begin():
        user = User(email=f'pg-validation-{uuid.uuid4().hex}@example.com', full_name='Validation', password_hash='unusable')
        db.add(user); db.flush()
        monitor = Monitor(user_id=user.id, name='Validation', url='https://example.com', interval_seconds=30, timeout_seconds=10)
        db.add(monitor); db.flush()
        db.add(NotificationChannel(user_id=user.id, monitor_id=monitor.id, type='WEBHOOK', target='https://example.com'))
        job = MonitorJob(monitor.id, monitor.url, monitor.timeout_seconds, monitor.interval_seconds)
    for index, status in enumerate(['UP', 'DOWN', 'DOWN', 'DOWN', 'DOWN', 'UP', 'UP']):
        assert persist_check(sessions, job, CheckResult(status, 200 if status == 'UP' else 500, 10))
        with sessions() as db:
            count = db.scalar(select(func.count()).select_from(Incident))
            assert count == (0 if index < 3 else 1)
            if index >= 3:
                assert db.scalar(select(Incident.status)) == ('OPEN' if index < 5 else 'RESOLVED')
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(Incident)) == 1
        assert db.scalar(select(Incident.status)) == 'RESOLVED'
        deliveries = list(db.scalars(select(NotificationDelivery)))
        assert sorted(item.event_type for item in deliveries) == ['INCIDENT_OPENED', 'INCIDENT_RESOLVED']
        original = deliveries[0]
        db.add(NotificationDelivery(incident_id=original.incident_id, channel_id=original.channel_id, event_type=original.event_type, payload=original.payload))
        try:
            db.commit()
            raise AssertionError('Unique constraint did not reject duplicate')
        except IntegrityError:
            db.rollback()
    now = datetime.now(timezone.utc) + timedelta(seconds=1)
    # Concurrent workers claim different rows, each only once.
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda _: claim_one(sessions, now), range(2)))
    assert all(claims) and len({claim.id for claim in claims}) == 2
    for claim in claims:
        finish(sessions, claim, 'delivery_transport_error', now - timedelta(minutes=2))
    sent = []
    async def transport(client, target, payload, delivery_id):
        assert engine.pool.checkedout() == 0, 'DB transaction held during external send'
        sent.append(payload['event'])
    async def deliver():
        with patch('app.notifications.worker.send_webhook', side_effect=transport):
            async with create_client(1) as client:
                await run_delivery_cycle(sessions, client, Settings())
    asyncio.run(deliver())
    assert sorted(sent) == ['INCIDENT_OPENED', 'INCIDENT_RESOLVED']
    with sessions() as db:
        assert set(db.scalars(select(NotificationDelivery.status))) == {'SENT'}
        assert set(db.scalars(select(NotificationDelivery.attempt_count))) == {2}
    from app.services.retention import cleanup
    with sessions() as db, db.begin():
        old = datetime.now(timezone.utc) - timedelta(days=31)
        for check in db.scalars(select(MonitorCheck)):
            check.checked_at = old
        for delivery in db.scalars(select(NotificationDelivery)):
            delivery.created_at = old
    assert cleanup(sessions, Settings(), datetime.now(timezone.utc)) == (7, 2)
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(Incident)) == 1
    print('PASS: PostgreSQL retention preserves incidents')
    print('PASS: PostgreSQL lifecycle, unique outbox, concurrent claims, retries, no transaction during send')


def main() -> None:
    url = make_url(os.environ['DATABASE_URL'])
    name = 'statuswatch_notification_test_' + uuid.uuid4().hex
    admin = create_engine(url, isolation_level='AUTOCOMMIT')
    engine = None
    created = False
    try:
        with admin.connect() as connection:
            connection.connection.driver_connection.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        created = True
        test_url = url.set(database=name)
        subprocess.run(['alembic', 'upgrade', 'head'], env={**os.environ, 'DATABASE_URL': test_url.render_as_string(hide_password=False)}, check=True)
        engine = create_engine(test_url)
        verify(engine)
    finally:
        if engine is not None: engine.dispose()
        if created:
            with admin.connect() as connection:
                connection.connection.driver_connection.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(name)))
        admin.dispose()


if __name__ == '__main__':
    main()

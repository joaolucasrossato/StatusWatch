import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.models import Incident, MonitorCheck, NotificationDelivery
from app.monitoring.checker import create_client
from app.notifications.worker import claim_one, finish, run_delivery_cycle
from test_incidents import create_job, create_monitor, persist
from test_notification_channels import create


@pytest.fixture
def outbox(client, accounts, db):
    monitor = create_monitor(client, accounts[0][1])
    response = create(client, accounts, monitor)
    assert response.status_code == 201
    return sessionmaker(bind=db.bind), create_job(monitor), response.json()


def rows(db):
    db.expire_all()
    return list(db.scalars(select(NotificationDelivery).order_by(NotificationDelivery.created_at, NotificationDelivery.event_type)))


def open_incident(sessions, job):
    for _ in range(3):
        persist(sessions, job, 'DOWN')


def test_transition_events_and_snapshots(outbox, db):
    sessions, job, _ = outbox
    persist(sessions, job, 'UP')
    persist(sessions, job, 'DOWN')
    persist(sessions, job, 'DOWN')
    assert rows(db) == []
    persist(sessions, job, 'DOWN')
    assert len(rows(db)) == 1
    persist(sessions, job, 'DOWN')
    assert len(rows(db)) == 1
    persist(sessions, job, 'UP')
    persist(sessions, job, 'UP')
    deliveries = rows(db)
    assert [r.event_type for r in deliveries] == ['INCIDENT_OPENED', 'INCIDENT_RESOLVED']
    assert deliveries[0].payload['incident']['status'] == 'OPEN'
    assert deliveries[0].payload['incident']['resolved_at'] is None
    assert deliveries[1].payload['incident']['status'] == 'RESOLVED'
    assert deliveries[1].payload['incident']['resolved_at'] is not None


def test_outbox_rolls_back_with_check_and_incident(outbox, db, monkeypatch):
    import app.services.incidents as service
    sessions, job, _ = outbox
    persist(sessions, job, 'DOWN'); persist(sessions, job, 'DOWN')
    original = service.enqueue_transition
    def fail(session, incident, event):
        original(session, incident, event)
        raise RuntimeError('abort transaction')
    monkeypatch.setattr(service, 'enqueue_transition', fail)
    with pytest.raises(RuntimeError):
        persist(sessions, job, 'DOWN')
    assert rows(db) == []
    assert list(db.scalars(select(Incident))) == []
    assert len(list(db.scalars(select(MonitorCheck)))) == 2


def test_unique_transition(outbox, db):
    sessions, job, _ = outbox
    open_incident(sessions, job)
    delivery = rows(db)[0]
    db.add(NotificationDelivery(incident_id=delivery.incident_id, channel_id=delivery.channel_id,
                               event_type=delivery.event_type, payload=delivery.payload))
    with pytest.raises(IntegrityError): db.commit()
    db.rollback()
    assert len(rows(db)) == 1


def test_preferences_and_disabled_channel(client, accounts, outbox, db):
    sessions, job, channel = outbox
    path = '/notification-channels/' + channel['id']
    client.patch(path, headers=accounts[0][1], json={'notify_on_open': False})
    open_incident(sessions, job)
    assert rows(db) == []
    persist(sessions, job, 'UP')
    assert [r.event_type for r in rows(db)] == ['INCIDENT_RESOLVED']
    client.patch(path, headers=accounts[0][1], json={'is_active': False})
    open_incident(sessions, job); persist(sessions, job, 'UP')
    assert len(rows(db)) == 1


def test_retry_claim_and_terminal_failure(outbox, db):
    sessions, monitor_job, _ = outbox
    open_incident(sessions, monitor_job)
    now = datetime.now(timezone.utc) + timedelta(seconds=1)
    first = claim_one(sessions, now)
    assert first is not None
    assert claim_one(sessions, now) is None
    finish(sessions, first, 'delivery_transport_error', now)
    delivery = rows(db)[0]
    assert delivery.status == 'PENDING' and delivery.attempt_count == 1
    assert claim_one(sessions, now + timedelta(seconds=59)) is None
    second = claim_one(sessions, now + timedelta(seconds=60))
    finish(sessions, second, 'delivery_transport_error', now + timedelta(seconds=60))
    assert rows(db)[0].attempt_count == 2
    assert claim_one(sessions, now + timedelta(seconds=359)) is None
    third = claim_one(sessions, now + timedelta(seconds=360))
    finish(sessions, third, 'delivery_transport_error', now + timedelta(seconds=360))
    assert rows(db)[0].status == 'FAILED'
    assert rows(db)[0].attempt_count == 3
    assert claim_one(sessions, now + timedelta(days=1)) is None


def test_abandoned_claim_recovery_and_stale_completion(outbox, db):
    sessions, monitor_job, _ = outbox
    open_incident(sessions, monitor_job)
    now = datetime.now(timezone.utc) + timedelta(seconds=1)
    old = claim_one(sessions, now)
    current = claim_one(sessions, now + timedelta(seconds=301))
    assert current.claim_token != old.claim_token
    finish(sessions, old, None, now)
    assert rows(db)[0].status == 'PROCESSING'
    finish(sessions, current, None, now + timedelta(seconds=302))
    assert rows(db)[0].status == 'SENT'
    assert rows(db)[0].sent_at is not None


def test_expired_final_claim_and_disabled_pending(outbox, db, client, accounts):
    sessions, monitor_job, channel = outbox
    open_incident(sessions, monitor_job)
    now = datetime.now(timezone.utc) + timedelta(seconds=1)
    for seconds in (0, 301, 602): assert claim_one(sessions, now + timedelta(seconds=seconds)) is not None
    assert claim_one(sessions, now + timedelta(seconds=903)) is None
    assert rows(db)[0].status == 'FAILED'
    persist(sessions, monitor_job, 'UP')
    client.patch('/notification-channels/' + channel['id'], headers=accounts[0][1], json={'is_active': False})
    assert claim_one(sessions, now + timedelta(seconds=904)) is None
    assert all(item.status == 'FAILED' for item in rows(db))


def test_sender_failure_persists_and_success_commits_without_open_transaction(outbox, db, monkeypatch, caplog):
    sessions, monitor_job, _ = outbox
    open_incident(sessions, monitor_job)
    def failed(*args): raise RuntimeError('must-not-log-sensitive-value')
    monkeypatch.setattr('app.notifications.worker.send_email', failed)
    async def run():
        async with create_client(1) as client:
            await run_delivery_cycle(sessions, client, Settings())
    asyncio.run(run())
    delivery = rows(db)[0]
    assert delivery.status == 'PENDING' and delivery.attempt_count == 1
    assert delivery.last_error == 'delivery_transport_error'
    assert 'must-not-log-sensitive-value' not in caplog.text
    delivery.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    def sent(*args):
        # Sending can open a new session: the claim was committed already.
        with sessions() as session:
            current = session.get(NotificationDelivery, delivery.id)
            assert current.status == 'PROCESSING' and current.attempt_count == 2
    monkeypatch.setattr('app.notifications.worker.send_email', sent)
    asyncio.run(run())
    assert rows(db)[0].status == 'SENT'


def test_deliveries_api_filters_pagination_and_ownership(outbox, db, client, accounts):
    sessions, job, channel = outbox
    open_incident(sessions, job); persist(sessions, job, 'UP')
    headers = accounts[0][1]
    response = client.get('/notification-deliveries?limit=1&offset=1', headers=headers)
    assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
    assert response.json()['total'] == 2 and len(response.json()['items']) == 1
    assert 'payload' not in response.json()['items'][0]
    assert client.get('/notification-deliveries?status=SENT', headers=headers).json()['total'] == 0
    assert client.get('/notification-deliveries?event_type=INCIDENT_OPENED', headers=headers).json()['total'] == 1
    incident_id = rows(db)[0].incident_id
    assert client.get(f'/incidents/{incident_id}/notification-deliveries', headers=headers).json()['total'] == 2
    assert client.get('/notification-deliveries', headers=accounts[1][1]).json()['total'] == 0
    assert client.get(f'/incidents/{incident_id}/notification-deliveries', headers=accounts[1][1]).status_code == 404
    assert client.get(f'/notification-deliveries?monitor_id={job.id}', headers=accounts[1][1]).status_code == 404
    for query in ('status=INVALID', 'event_type=INVALID', 'limit=101', 'offset=-1'):
        assert client.get('/notification-deliveries?' + query, headers=headers).status_code == 422
    assert client.post('/notification-deliveries', headers=headers, json={}).status_code == 405
    client.delete('/notification-channels/' + channel['id'], headers=headers)
    assert client.get('/notification-deliveries', headers=headers).json()['total'] == 0


def test_delivery_loop_recovers_after_database_failure(monkeypatch, caplog):
    from app.notifications.worker import delivery_loop
    async def run():
        stop = asyncio.Event()
        calls = 0
        async def cycle(*args):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError('private database details')
            stop.set()
        monkeypatch.setattr('app.notifications.worker.run_delivery_cycle', cycle)
        await delivery_loop(None, None, Settings(worker_poll_interval_seconds=0.1), stop)
        assert calls == 2
    asyncio.run(run())
    assert 'notification_delivery_cycle_failed' in caplog.text
    assert 'private database details' not in caplog.text


@pytest.mark.parametrize('kind,error_name', [('EMAIL', 'timeout'), ('EMAIL', 'smtp'),
                                          ('WEBHOOK', 'timeout'), ('WEBHOOK', 'protocol')])
def test_transport_failures_leave_delivery_retryable(outbox, db, monkeypatch, kind, error_name):
    import smtplib
    import httpx
    from app.models import NotificationChannel
    sessions, job, channel = outbox
    record = db.get(NotificationChannel, uuid.UUID(channel['id']))
    record.type = kind
    record.target = 'https://example.com' if kind == 'WEBHOOK' else 'alerts@example.com'
    db.commit()
    open_incident(sessions, job)
    error = (httpx.ReadTimeout('private destination') if kind == 'WEBHOOK' and error_name == 'timeout'
             else httpx.RemoteProtocolError('private response') if error_name == 'protocol'
             else smtplib.SMTPException('private credentials') if error_name == 'smtp'
             else TimeoutError('private SMTP timeout'))
    if kind == 'EMAIL':
        def fail(*args):
            raise error
        monkeypatch.setattr('app.notifications.worker.send_email', fail)
    else:
        monkeypatch.setattr('app.notifications.worker.send_webhook', AsyncMock(side_effect=error))
    async def run():
        async with create_client(1) as client:
            await run_delivery_cycle(sessions, client, Settings())
    asyncio.run(run())
    delivery = rows(db)[0]
    assert delivery.status == 'PENDING'
    assert delivery.attempt_count == 1
    assert delivery.last_error == 'delivery_transport_error'


def notification_snapshot(metric_value, kind):
    labels = {'channel_type': kind}
    return {
        **{outcome: metric_value('notification_delivery_attempts_total', **labels, outcome=outcome)
           for outcome in ('success', 'error', 'cancelled')},
        **{status: metric_value('notification_deliveries_total', **labels, status=status)
           for status in ('SENT', 'FAILED')},
        'retry': metric_value('notification_delivery_retries_total', **labels),
        'duration': metric_value('notification_delivery_duration_seconds_count', **labels),
    }


@pytest.mark.parametrize('kind', ['EMAIL', 'WEBHOOK'])
@pytest.mark.parametrize('outcome,attempts,status', [
    ('success', 0, 'SENT'), ('error', 0, 'PENDING'), ('error', 2, 'FAILED'),
    ('cancelled', 0, 'PROCESSING'),
])
def test_delivery_metrics(outbox, db, monkeypatch, metric_value, kind, outcome, attempts, status):
    from app.models import NotificationChannel

    sessions, job, channel = outbox
    db.get(NotificationChannel, uuid.UUID(channel['id'])).type = kind
    db.commit()
    open_incident(sessions, job)
    rows(db)[0].attempt_count = attempts
    db.commit()

    def send(*args):
        if outcome == 'error':
            raise RuntimeError('private transport details')
        if outcome == 'cancelled':
            raise asyncio.CancelledError
    monkeypatch.setattr('app.notifications.worker.send_email', send)
    monkeypatch.setattr('app.notifications.worker.send_webhook', AsyncMock(side_effect=send))
    before = notification_snapshot(metric_value, kind)
    if outcome == 'cancelled':
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(run_delivery_cycle(sessions, None, Settings()))
    else:
        asyncio.run(run_delivery_cycle(sessions, None, Settings()))
    after = notification_snapshot(metric_value, kind)
    expected = {key: 0 for key in before}
    expected.update({outcome: 1, 'duration': 1})
    if status in ('SENT', 'FAILED'):
        expected[status] = 1
    elif status == 'PENDING':
        expected['retry'] = 1
    assert {key: after[key] - before[key] for key in before} == expected
    assert rows(db)[0].status == status


@pytest.mark.parametrize('reason', ['disabled', 'expired'])
@pytest.mark.parametrize('rollback', [False, True])
def test_claim_terminal_metrics_after_commit(outbox, db, metric_value, fail_commit, reason, rollback):
    from app.models import NotificationChannel

    sessions, job, channel = outbox
    open_incident(sessions, job)
    if reason == 'disabled':
        db.get(NotificationChannel, uuid.UUID(channel['id'])).is_active = False
        db.commit()
    else:
        delivery = rows(db)[0]
        delivery.status = 'PROCESSING'
        delivery.attempt_count = 3
        delivery.claim_token = uuid.uuid4()
        db.commit()
    before = notification_snapshot(metric_value, 'EMAIL')
    now = datetime.now(timezone.utc) + timedelta(seconds=1)
    if rollback:
        fail_commit(sessions)
        with pytest.raises(RuntimeError, match='commit failed'):
            claim_one(sessions, now)
        assert rows(db)[0].status != 'FAILED'
    else:
        assert claim_one(sessions, now) is None
        assert rows(db)[0].status == 'FAILED'
        assert claim_one(sessions, now) is None
    after = notification_snapshot(metric_value, 'EMAIL')
    expected = {key: 0 for key in before}
    expected['FAILED'] = int(not rollback)
    assert {key: after[key] - before[key] for key in before} == expected


@pytest.mark.parametrize('error,attempts', [(None, 0), ('delivery_transport_error', 0),
                                          ('delivery_transport_error', 2)])
def test_finish_commit_failure_does_not_count_persisted_state(
    outbox, db, metric_value, fail_commit, error, attempts,
):
    sessions, job, _ = outbox
    open_incident(sessions, job)
    rows(db)[0].attempt_count = attempts
    db.commit()
    now = datetime.now(timezone.utc) + timedelta(seconds=1)
    claimed = claim_one(sessions, now)
    before = notification_snapshot(metric_value, 'EMAIL')
    fail_commit(sessions)
    with pytest.raises(RuntimeError, match='commit failed'):
        finish(sessions, claimed, error, now)
    assert notification_snapshot(metric_value, 'EMAIL') == before
    assert rows(db)[0].status == 'PROCESSING'


def test_stale_finish_does_not_count_delivery(outbox, metric_value):
    sessions, job, _ = outbox
    open_incident(sessions, job)
    now = datetime.now(timezone.utc) + timedelta(seconds=1)
    stale = claim_one(sessions, now)
    current = claim_one(sessions, now + timedelta(seconds=301))
    before = notification_snapshot(metric_value, 'EMAIL')
    assert finish(sessions, stale, None, now) is None
    assert notification_snapshot(metric_value, 'EMAIL') == before
    assert finish(sessions, current, None, now) == 'SENT'
    after = notification_snapshot(metric_value, 'EMAIL')
    assert after['SENT'] - before['SENT'] == 1
    assert finish(sessions, current, None, now) is None
    assert notification_snapshot(metric_value, 'EMAIL') == after


def test_deleted_channel_cascades_without_false_terminal_metric(outbox, db, metric_value):
    from app.models import NotificationChannel

    sessions, job, channel = outbox
    open_incident(sessions, job)
    before = notification_snapshot(metric_value, 'EMAIL')
    db.delete(db.get(NotificationChannel, uuid.UUID(channel['id'])))
    db.commit()
    assert claim_one(sessions, datetime.now(timezone.utc) + timedelta(seconds=1)) is None
    assert rows(db) == []
    assert notification_snapshot(metric_value, 'EMAIL') == before


def test_cancelled_waiter_still_counts_committed_finish(outbox, db, metric_value):
    import threading
    from sqlalchemy import event

    sessions, job, _ = outbox
    open_incident(sessions, job)
    now = datetime.now(timezone.utc) + timedelta(seconds=1)
    claimed = claim_one(sessions, now)
    before = notification_snapshot(metric_value, 'EMAIL')
    release = threading.Event()

    async def run():
        committing = asyncio.Event()
        loop = asyncio.get_running_loop()

        def before_commit(session):
            loop.call_soon_threadsafe(committing.set)
            assert release.wait(timeout=5)

        event.listen(sessions, 'before_commit', before_commit)
        task = asyncio.create_task(asyncio.to_thread(finish, sessions, claimed, None, now))
        try:
            await asyncio.wait_for(committing.wait(), timeout=5)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            release.set()

    # asyncio.run also waits for the executor thread to finish its transaction.
    asyncio.run(run())
    assert rows(db)[0].status == 'SENT'
    after = notification_snapshot(metric_value, 'EMAIL')
    assert after == {**before, 'SENT': before['SENT'] + 1}

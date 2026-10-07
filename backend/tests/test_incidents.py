import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models import Incident, MonitorCheck
from app.monitoring.checker import CheckResult
from app.monitoring.scheduler import MonitorJob, persist_check


def create_monitor(client, headers):
    response = client.post(
        "/monitors",
        headers=headers,
        json={
            "name": "Incident Monitor",
            "url": "https://example.com",
            "interval_seconds": 30,
            "timeout_seconds": 10,
        },
    )

    assert response.status_code == 201

    return response.json()


def create_job(monitor):
    return MonitorJob(
        id=uuid.UUID(monitor["id"]),
        url=monitor["url"],
        timeout_seconds=monitor["timeout_seconds"],
        interval_seconds=monitor["interval_seconds"],
    )


def incidents(db):
    db.expire_all()

    return list(
        db.scalars(
            select(Incident)
            .order_by(Incident.started_at.asc())
        )
    )


def checks(db):
    db.expire_all()

    return list(
        db.scalars(
            select(MonitorCheck)
            .order_by(MonitorCheck.checked_at.asc())
        )
    )


def persist(
    sessions,
    job,
    status,
):
    if status == "UP":
        result = CheckResult(
            status="UP",
            http_status_code=200,
            response_time_ms=10,
        )
    else:
        result = CheckResult(
            status="DOWN",
            http_status_code=500,
            response_time_ms=10,
        )

    assert persist_check(
        sessions,
        job,
        result,
    )


def test_successful_check_does_not_create_incident(
    client,
    accounts,
    db,
):
    monitor = create_monitor(
        client,
        accounts[0][1],
    )

    sessions = sessionmaker(bind=db.bind)
    job = create_job(monitor)

    persist(sessions, job, "UP")

    assert len(checks(db)) == 1
    assert incidents(db) == []


def test_incident_opens_after_three_consecutive_failures(
    client,
    accounts,
    db,
):
    monitor = create_monitor(
        client,
        accounts[0][1],
    )

    sessions = sessionmaker(bind=db.bind)
    job = create_job(monitor)

    persist(sessions, job, "DOWN")

    assert len(checks(db)) == 1
    assert incidents(db) == []

    persist(sessions, job, "DOWN")

    assert len(checks(db)) == 2
    assert incidents(db) == []

    persist(sessions, job, "DOWN")

    stored_checks = checks(db)
    stored_incidents = incidents(db)

    assert len(stored_checks) == 3
    assert len(stored_incidents) == 1

    incident = stored_incidents[0]

    assert incident.status == "OPEN"
    assert incident.started_at == stored_checks[0].checked_at
    assert incident.opened_at == stored_checks[2].checked_at
    assert incident.resolved_at is None


def test_additional_failures_do_not_duplicate_open_incident(
    client,
    accounts,
    db,
):
    monitor = create_monitor(
        client,
        accounts[0][1],
    )

    sessions = sessionmaker(bind=db.bind)
    job = create_job(monitor)

    persist(sessions, job, "DOWN")
    persist(sessions, job, "DOWN")
    persist(sessions, job, "DOWN")

    original = incidents(db)[0]
    original_id = original.id

    persist(sessions, job, "DOWN")
    persist(sessions, job, "DOWN")

    stored_incidents = incidents(db)

    assert len(stored_incidents) == 1
    assert stored_incidents[0].id == original_id
    assert stored_incidents[0].status == "OPEN"
    assert stored_incidents[0].resolved_at is None


def test_up_resolves_open_incident(
    client,
    accounts,
    db,
):
    monitor = create_monitor(
        client,
        accounts[0][1],
    )

    sessions = sessionmaker(bind=db.bind)
    job = create_job(monitor)

    persist(sessions, job, "DOWN")
    persist(sessions, job, "DOWN")
    persist(sessions, job, "DOWN")

    persist(sessions, job, "UP")

    stored_checks = checks(db)
    stored_incidents = incidents(db)

    assert len(stored_incidents) == 1

    incident = stored_incidents[0]

    assert incident.status == "RESOLVED"
    assert incident.resolved_at == stored_checks[-1].checked_at


def test_new_incident_requires_new_three_failure_sequence(
    client,
    accounts,
    db,
):
    monitor = create_monitor(
        client,
        accounts[0][1],
    )

    sessions = sessionmaker(bind=db.bind)
    job = create_job(monitor)

    # First incident.
    persist(sessions, job, "DOWN")
    persist(sessions, job, "DOWN")
    persist(sessions, job, "DOWN")
    persist(sessions, job, "UP")

    stored_incidents = incidents(db)

    assert len(stored_incidents) == 1
    assert stored_incidents[0].status == "RESOLVED"

    # First failure after recovery.
    persist(sessions, job, "DOWN")

    assert len(incidents(db)) == 1

    # Second failure after recovery.
    persist(sessions, job, "DOWN")

    assert len(incidents(db)) == 1

    # Third consecutive failure opens a new incident.
    persist(sessions, job, "DOWN")

    stored_incidents = incidents(db)

    assert len(stored_incidents) == 2

    first_incident = stored_incidents[0]
    second_incident = stored_incidents[1]

    assert first_incident.status == "RESOLVED"
    assert first_incident.resolved_at is not None

    assert second_incident.status == "OPEN"
    assert second_incident.resolved_at is None

    stored_checks = checks(db)

    assert second_incident.started_at == stored_checks[-3].checked_at
    assert second_incident.opened_at == stored_checks[-1].checked_at


def test_success_resets_consecutive_failure_sequence(
    client,
    accounts,
    db,
):
    monitor = create_monitor(
        client,
        accounts[0][1],
    )

    sessions = sessionmaker(bind=db.bind)
    job = create_job(monitor)

    persist(sessions, job, "DOWN")
    persist(sessions, job, "DOWN")

    # Recovery before the threshold resets the sequence.
    persist(sessions, job, "UP")

    persist(sessions, job, "DOWN")
    persist(sessions, job, "DOWN")

    assert incidents(db) == []

    persist(sessions, job, "DOWN")

    stored_incidents = incidents(db)

    assert len(stored_incidents) == 1
    assert stored_incidents[0].status == "OPEN"

def test_check_is_rolled_back_when_incident_processing_fails(
    client,
    accounts,
    db,
    monkeypatch,
):
    import app.monitoring.scheduler as scheduler

    monitor = create_monitor(
        client,
        accounts[0][1],
    )

    sessions = sessionmaker(bind=db.bind)
    job = create_job(monitor)

    def fail_incident_processing(_db, _check):
        raise RuntimeError("incident processing failed")

    monkeypatch.setattr(
        scheduler,
        "process_incident_for_check",
        fail_incident_processing,
    )

    result = CheckResult(
        status="DOWN",
        http_status_code=500,
        response_time_ms=10,
    )

    with pytest.raises(
        RuntimeError,
        match="incident processing failed",
    ):
        scheduler.persist_check(
            sessions,
            job,
            result,
        )

    db.expire_all()

    stored_checks = list(
        db.scalars(
            select(MonitorCheck)
        )
    )

    stored_incidents = list(
        db.scalars(
            select(Incident)
        )
    )

    assert stored_checks == []
    assert stored_incidents == []

@pytest.mark.parametrize('event_name', ['opened', 'resolved'])
@pytest.mark.parametrize('rollback', [False, True])
def test_transition_metrics_only_after_commit(
    client, accounts, db, metric_value, fail_commit, event_name, rollback,
):
    monitor = create_monitor(client, accounts[0][1])
    job = create_job(monitor)
    sessions = sessionmaker(bind=db.bind)
    for _ in range(2 if event_name == 'opened' else 3):
        persist(sessions, job, 'DOWN')
    before = {event: metric_value('incident_transitions_total', event=event)
              for event in ('opened', 'resolved')}
    if rollback:
        fail_commit(sessions)
        with pytest.raises(RuntimeError, match='commit failed'):
            persist(sessions, job, 'DOWN' if event_name == 'opened' else 'UP')
    else:
        persist(sessions, job, 'DOWN' if event_name == 'opened' else 'UP')
        # Repeating the same state must not report another transition.
        persist(sessions, job, 'DOWN' if event_name == 'opened' else 'UP')
    for event in before:
        assert metric_value('incident_transitions_total', event=event) - before[event] == int(
            not rollback and event == event_name
        )
    stored = incidents(db)
    if event_name == 'opened':
        assert len(stored) == int(not rollback)
    else:
        assert stored[0].status == ('OPEN' if rollback else 'RESOLVED')

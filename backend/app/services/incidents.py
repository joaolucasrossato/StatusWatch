import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.incident import Incident
from app.models.monitor_check import MonitorCheck
from app.services.notification_outbox import enqueue_transition

INCIDENT_FAILURE_THRESHOLD = 3


def get_open_incident(
    db: Session,
    monitor_id: uuid.UUID,
) -> Incident | None:
    return db.scalar(
        select(Incident).where(
            Incident.monitor_id == monitor_id,
            Incident.status == "OPEN",
        )
    )


def process_incident_for_check(
    db: Session,
    check: MonitorCheck,
) -> Incident | None:
    """Update the incident lifecycle for a persisted monitor check."""

    open_incident = get_open_incident(db, check.monitor_id)

    # The first successful check resolves the current incident.
    if check.status == "UP":
        if open_incident is None:
            return None

        open_incident.status = "RESOLVED"
        open_incident.resolved_at = check.checked_at
        enqueue_transition(db, open_incident, "INCIDENT_RESOLVED")
        return open_incident

    if check.status != "DOWN":
        raise ValueError(
            f"Unsupported monitor check status: {check.status}"
        )

    # A monitor can have at most one open incident.
    if open_incident is not None:
        return open_incident

    recent_checks = list(
        db.scalars(
            select(MonitorCheck)
            .where(MonitorCheck.monitor_id == check.monitor_id)
            .order_by(
                MonitorCheck.checked_at.desc(),
                MonitorCheck.id.desc(),
            )
            .limit(INCIDENT_FAILURE_THRESHOLD)
        )
    )

    if len(recent_checks) < INCIDENT_FAILURE_THRESHOLD:
        return None

    if not all(
        item.status == "DOWN"
        for item in recent_checks
    ):
        return None

    first_failure = recent_checks[-1]

    incident = Incident(
        monitor_id=check.monitor_id,
        status="OPEN",
        started_at=first_failure.checked_at,
        opened_at=check.checked_at,
    )

    db.add(incident)
    enqueue_transition(db, incident, "INCIDENT_OPENED")

    return incident

class IncidentNotFoundError(Exception):
    pass


class MonitorNotFoundError(Exception):
    pass


def _require_owned_monitor(
    db: Session,
    *,
    monitor_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    from app.models.monitor import Monitor

    monitor_id_result = db.scalar(
        select(Monitor.id).where(
            Monitor.id == monitor_id,
            Monitor.user_id == user_id,
        )
    )

    if monitor_id_result is None:
        raise MonitorNotFoundError


def list_incidents(
    db: Session,
    *,
    user_id: uuid.UUID,
    incident_status: str | None,
    limit: int,
    offset: int,
) -> tuple[int, list[Incident]]:
    from sqlalchemy import func

    from app.models.monitor import Monitor

    filters = [
        Monitor.user_id == user_id,
    ]

    if incident_status is not None:
        filters.append(Incident.status == incident_status)

    count_statement = (
        select(func.count(Incident.id))
        .join(
            Monitor,
            Monitor.id == Incident.monitor_id,
        )
        .where(*filters)
    )

    total = db.scalar(count_statement) or 0

    statement = (
        select(Incident)
        .join(
            Monitor,
            Monitor.id == Incident.monitor_id,
        )
        .where(*filters)
        .order_by(
            Incident.started_at.desc(),
            Incident.id.desc(),
        )
        .offset(offset)
        .limit(limit)
    )

    items = list(db.scalars(statement).all())

    return int(total), items


def get_owned_incident(
    db: Session,
    *,
    incident_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Incident:
    from app.models.monitor import Monitor

    incident = db.scalar(
        select(Incident)
        .join(
            Monitor,
            Monitor.id == Incident.monitor_id,
        )
        .where(
            Incident.id == incident_id,
            Monitor.user_id == user_id,
        )
    )

    if incident is None:
        raise IncidentNotFoundError

    return incident


def list_monitor_incidents(
    db: Session,
    *,
    monitor_id: uuid.UUID,
    user_id: uuid.UUID,
    incident_status: str | None,
    limit: int,
    offset: int,
) -> tuple[int, list[Incident]]:
    from sqlalchemy import func

    _require_owned_monitor(
        db,
        monitor_id=monitor_id,
        user_id=user_id,
    )

    filters = [
        Incident.monitor_id == monitor_id,
    ]

    if incident_status is not None:
        filters.append(Incident.status == incident_status)

    count_statement = (
        select(func.count(Incident.id))
        .where(*filters)
    )

    total = db.scalar(count_statement) or 0

    statement = (
        select(Incident)
        .where(*filters)
        .order_by(
            Incident.started_at.desc(),
            Incident.id.desc(),
        )
        .offset(offset)
        .limit(limit)
    )

    items = list(db.scalars(statement).all())

    return int(total), items
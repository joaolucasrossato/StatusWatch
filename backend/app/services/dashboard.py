from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.models.monitor import Monitor
from app.models.monitor_check import MonitorCheck

from app.models.incident import Incident


class MonitorNotFoundError(Exception):
    pass


def _require_owned_monitor(
    db: Session,
    *,
    monitor_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Monitor:
    statement = select(Monitor).where(
        Monitor.id == monitor_id,
        Monitor.user_id == user_id,
    )

    monitor = db.scalar(statement)

    if monitor is None:
        raise MonitorNotFoundError

    return monitor


def get_dashboard_summary(
    db: Session,
    *,
    user_id: uuid.UUID,
) -> dict:
    ranked_checks = (
        select(
            MonitorCheck.monitor_id.label("monitor_id"),
            MonitorCheck.status.label("status"),
            func.row_number()
            .over(
                partition_by=MonitorCheck.monitor_id,
                order_by=(MonitorCheck.checked_at.desc(), MonitorCheck.id.desc()),
            )
            .label("row_number"),
        )
        .subquery()
    )

    statement = (
        select(
            Monitor.is_active,
            ranked_checks.c.status,
        )
        .outerjoin(
            ranked_checks,
            and_(
                ranked_checks.c.monitor_id == Monitor.id,
                ranked_checks.c.row_number == 1,
            ),
        )
        .where(Monitor.user_id == user_id)
    )

    rows = db.execute(statement).all()

    total_monitors = len(rows)
    active_monitors = 0
    paused_monitors = 0
    up_monitors = 0
    down_monitors = 0
    pending_monitors = 0

    for is_active, latest_status in rows:
        if not is_active:
            paused_monitors += 1
            continue

        active_monitors += 1

        if latest_status is None:
            pending_monitors += 1
        elif str(latest_status) == "UP":
            up_monitors += 1
        elif str(latest_status) == "DOWN":
            down_monitors += 1
        else:
            pending_monitors += 1

    since = datetime.now(timezone.utc) - timedelta(hours=24)

    checks_statement = (
        select(
            func.count(MonitorCheck.id),
            func.avg(MonitorCheck.response_time_ms),
        )
        .join(
            Monitor,
            Monitor.id == MonitorCheck.monitor_id,
        )
        .where(
            Monitor.user_id == user_id,
            MonitorCheck.checked_at >= since,
        )
    )

    checks_count, average_response_time = db.execute(
        checks_statement
    ).one()

    average_response_time_ms = (
        round(float(average_response_time), 2)
        if average_response_time is not None
        else None
    )

    open_incidents_statement = (
        select(func.count(Incident.id))
        .join(
            Monitor,
            Monitor.id == Incident.monitor_id,
        )
        .where(
            Monitor.user_id == user_id,
            Incident.status == "OPEN",
        )
    )

    open_incidents = db.scalar(open_incidents_statement) or 0

    return {
        "total_monitors": total_monitors,
        "active_monitors": active_monitors,
        "paused_monitors": paused_monitors,
        "up_monitors": up_monitors,
        "down_monitors": down_monitors,
        "pending_monitors": pending_monitors,
        "open_incidents": int(open_incidents),
        "checks_last_24h": int(checks_count or 0),
        "average_response_time_ms_24h": average_response_time_ms,
    }


def list_monitor_checks(
    db: Session,
    *,
    monitor_id: uuid.UUID,
    user_id: uuid.UUID,
    limit: int,
    offset: int,
) -> tuple[int, list[MonitorCheck]]:
    _require_owned_monitor(
        db,
        monitor_id=monitor_id,
        user_id=user_id,
    )

    count_statement = (
        select(func.count(MonitorCheck.id))
        .where(MonitorCheck.monitor_id == monitor_id)
    )

    total = db.scalar(count_statement) or 0

    checks_statement = (
        select(MonitorCheck)
        .where(MonitorCheck.monitor_id == monitor_id)
        .order_by(MonitorCheck.checked_at.desc(), MonitorCheck.id.desc())
        .offset(offset)
        .limit(limit)
    )

    checks = list(db.scalars(checks_statement).all())

    return int(total), checks


def get_monitor_stats(
    db: Session,
    *,
    monitor_id: uuid.UUID,
    user_id: uuid.UUID,
    window_hours: int,
) -> dict:
    _require_owned_monitor(
        db,
        monitor_id=monitor_id,
        user_id=user_id,
    )

    since = datetime.now(timezone.utc) - timedelta(hours=window_hours)

    statement = (
        select(
            func.count(MonitorCheck.id).label("total_checks"),
            func.sum(
                case(
                    (MonitorCheck.status == "UP", 1),
                    else_=0,
                )
            ).label("successful_checks"),
            func.sum(
                case(
                    (MonitorCheck.status == "DOWN", 1),
                    else_=0,
                )
            ).label("failed_checks"),
            func.avg(MonitorCheck.response_time_ms).label(
                "average_response_time"
            ),
            func.min(MonitorCheck.response_time_ms).label(
                "minimum_response_time"
            ),
            func.max(MonitorCheck.response_time_ms).label(
                "maximum_response_time"
            ),
        )
        .where(
            MonitorCheck.monitor_id == monitor_id,
            MonitorCheck.checked_at >= since,
        )
    )

    result = db.execute(statement).one()

    total_checks = int(result.total_checks or 0)
    successful_checks = int(result.successful_checks or 0)
    failed_checks = int(result.failed_checks or 0)

    uptime_percentage = None

    if total_checks > 0:
        uptime_percentage = round(
            successful_checks / total_checks * 100,
            2,
        )

    average_response_time_ms = (
        round(float(result.average_response_time), 2)
        if result.average_response_time is not None
        else None
    )

    return {
        "monitor_id": monitor_id,
        "window_hours": window_hours,
        "total_checks": total_checks,
        "successful_checks": successful_checks,
        "failed_checks": failed_checks,
        "uptime_percentage": uptime_percentage,
        "average_response_time_ms": average_response_time_ms,
        "minimum_response_time_ms": result.minimum_response_time,
        "maximum_response_time_ms": result.maximum_response_time,
    }
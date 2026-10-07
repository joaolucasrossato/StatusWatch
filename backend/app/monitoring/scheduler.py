import asyncio
import logging
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from time import perf_counter

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Monitor, MonitorCheck
from app.monitoring.checker import ERRORS, CheckResult, check_http
from app.services.incidents import process_incident_for_check
from app.observability.worker_metrics import (
    INCIDENT_TRANSITIONS,
    MONITOR_CHECK_DURATION,
    MONITOR_CHECK_FAILURES,
    MONITOR_CHECKS,
    SCHEDULER_CYCLE_DURATION,
    SCHEDULER_CYCLES,
)

logger = logging.getLogger(__name__)
SessionFactory = Callable[[], Session]


@dataclass(frozen=True)
class MonitorJob:
    id: uuid.UUID
    url: str
    timeout_seconds: int
    interval_seconds: int


def is_due(
    active: bool,
    latest: datetime | None,
    interval: int,
    now: datetime,
) -> bool:
    if not active:
        return False

    # SQLite test adapter strips timezone; PostgreSQL returns aware timestamps.
    if latest is not None and latest.tzinfo is None:
        latest = latest.replace(tzinfo=timezone.utc)

    return latest is None or now >= latest + timedelta(seconds=interval)


def due_monitors(
    sessions: SessionFactory,
    now: datetime,
) -> list[MonitorJob]:
    latest = (
        select(
            MonitorCheck.monitor_id,
            func.max(MonitorCheck.checked_at).label("at"),
        )
        .group_by(MonitorCheck.monitor_id)
        .subquery()
    )

    with sessions() as db:
        rows = db.execute(
            select(Monitor, latest.c.at)
            .outerjoin(
                latest,
                Monitor.id == latest.c.monitor_id,
            )
            .where(Monitor.is_active.is_(True))
        )

        return [
            MonitorJob(
                monitor.id,
                monitor.url,
                monitor.timeout_seconds,
                monitor.interval_seconds,
            )
            for monitor, checked_at in rows
            if is_due(
                monitor.is_active,
                checked_at,
                monitor.interval_seconds,
                now,
            )
        ]


def still_active(
    sessions: SessionFactory,
    job: MonitorJob,
) -> bool:
    with sessions() as db:
        return (
            db.scalar(
                select(Monitor.id).where(
                    Monitor.id == job.id,
                    Monitor.is_active.is_(True),
                    Monitor.url == job.url,
                    Monitor.timeout_seconds == job.timeout_seconds,
                    Monitor.interval_seconds == job.interval_seconds,
                )
            )
            is not None
        )


def persist_check(
    sessions: SessionFactory,
    job: MonitorJob,
    result: CheckResult,
) -> bool:
    # The lock serializes with pause/delete; no transaction spans network I/O.
    with sessions() as db, db.begin():
        monitor = db.scalar(
            select(Monitor)
            .where(Monitor.id == job.id)
            .with_for_update()
        )

        if (
            monitor is None
            or not monitor.is_active
            or monitor.url != job.url
            or monitor.timeout_seconds != job.timeout_seconds
            or monitor.interval_seconds != job.interval_seconds
        ):
            return False

        check = MonitorCheck(
            monitor_id=job.id,
            checked_at=datetime.now(timezone.utc),
            **asdict(result),
        )

        db.add(check)

        # Flush makes the current check visible to the incident query while
        # keeping check persistence and incident lifecycle in one transaction.
        db.flush()

        incident = process_incident_for_check(db, check)
        incident_id = incident.id if incident else None
        transition = None
        if incident is not None:
            if incident.opened_at == check.checked_at:
                transition = "incident_opened"
            elif incident.resolved_at == check.checked_at:
                transition = "incident_resolved"

    # The transaction has committed; count here even if run_cycle is cancelled
    # while awaiting this thread's result.
    MONITOR_CHECKS.labels(status=result.status).inc()
    if result.response_time_ms is not None:
        MONITOR_CHECK_DURATION.labels(status=result.status).observe(
            result.response_time_ms / 1000,
        )
    if result.status == "DOWN":
        if result.error_type in ERRORS:
            error_type = result.error_type
        elif result.error_type is None and result.http_status_code is not None:
            error_type = "http_error"
        else:
            error_type = "unexpected_error"
        MONITOR_CHECK_FAILURES.labels(error_type=error_type).inc()

    if transition:
        event = (
            "opened"
            if transition == "incident_opened"
            else "resolved"
        )

        INCIDENT_TRANSITIONS.labels(event=event).inc()

        logger.info(
            "%s monitor_id=%s incident_id=%s",
            transition,
            job.id,
            incident_id,
        )

    return True


async def run_cycle(
    sessions: SessionFactory,
    client: httpx.AsyncClient,
    concurrency: int,
    max_redirects: int,
) -> None:
    jobs = await asyncio.to_thread(
        due_monitors,
        sessions,
        datetime.now(timezone.utc),
    )

    logger.debug(
        "Scheduler cycle due=%s",
        len(jobs),
    )

    # A fixed number of consumers bounds tasks as well as network concurrency.
    iterator = iter(jobs)

    async def consume() -> None:
        for job in iterator:
            try:
                if not await asyncio.to_thread(
                    still_active,
                    sessions,
                    job,
                ):
                    continue

                logger.debug(
                    "Monitor check started monitor_id=%s",
                    job.id,
                )

                result = await check_http(
                    client,
                    job.url,
                    job.timeout_seconds,
                    max_redirects,
                )

                saved = await asyncio.to_thread(
                    persist_check,
                    sessions,
                    job,
                    result,
                )

                logger.info(
                    (
                        "monitor_check_completed monitor_id=%s "
                        "status=%s error_type=%s saved=%s"
                    ),
                    job.id,
                    result.status,
                    result.error_type,
                    saved,
                )

            except Exception as exc:
                logger.error(
                    "Monitor check failed monitor_id=%s class=%s",
                    job.id,
                    type(exc).__name__,
                )

    await asyncio.gather(
        *(
            consume()
            for _ in range(
                min(concurrency, len(jobs))
            )
        )
    )


async def scheduler_loop(
    sessions: SessionFactory,
    client: httpx.AsyncClient,
    stop: asyncio.Event,
    concurrency: int,
    poll_seconds: float,
    max_redirects: int,
) -> None:
    while not stop.is_set():
        started_at = perf_counter()

        try:
            await run_cycle(
                sessions,
                client,
                concurrency,
                max_redirects,
            )
        except Exception as exc:
            SCHEDULER_CYCLES.labels(result="error").inc()

            logger.error(
                "Scheduler cycle failed class=%s",
                type(exc).__name__,
            )
        else:
            SCHEDULER_CYCLES.labels(result="success").inc()
        finally:
            SCHEDULER_CYCLE_DURATION.observe(
                perf_counter() - started_at
            )

        try:
            await asyncio.wait_for(
                stop.wait(),
                timeout=poll_seconds,
            )
        except TimeoutError:
            continue

import asyncio
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Any

import httpx
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import NotificationChannel, NotificationDelivery
from app.monitoring.checker import DestinationError
from app.notifications.senders import DeliveryError, send_email, send_webhook
from app.observability.worker_metrics import (
    NOTIFICATION_DELIVERIES,
    NOTIFICATION_DELIVERY_ATTEMPTS,
    NOTIFICATION_DELIVERY_DURATION,
    NOTIFICATION_DELIVERY_RETRIES,
)

logger = logging.getLogger(__name__)
SessionFactory = Callable[[], Session]
MAX_ATTEMPTS = 3
LEASE_SECONDS = 300
RETRY_SECONDS = (60, 300)


@dataclass(frozen=True)
class DeliveryJob:
    id: uuid.UUID
    incident_id: uuid.UUID
    monitor_id: uuid.UUID
    claim_token: uuid.UUID
    kind: str
    target: str
    payload: dict[str, Any]


def claim_one(
    sessions: SessionFactory,
    now: datetime,
) -> DeliveryJob | None:
    job = None
    failed_channel_type = None
    with sessions() as db, db.begin():
        due = (
            NotificationDelivery.status.in_(["PENDING", "PROCESSING"]),
            NotificationDelivery.next_attempt_at <= now,
        )

        delivery = db.scalar(
            select(NotificationDelivery)
            .where(*due)
            .order_by(
                NotificationDelivery.next_attempt_at,
                NotificationDelivery.id,
            )
            .with_for_update(skip_locked=True)
            .limit(1)
        )

        if delivery is None:
            return None

        # Conditional update also protects claims on SQLite
        # (which ignores FOR UPDATE).
        token = uuid.uuid4()

        changed = db.execute(
            update(NotificationDelivery)
            .where(
                NotificationDelivery.id == delivery.id,
                *due,
            )
            .values(
                status="PROCESSING",
                claim_token=token,
                next_attempt_at=now + timedelta(seconds=LEASE_SECONDS),
            )
            .execution_options(synchronize_session="fetch")
        )

        if changed.rowcount != 1:
            return None

        channel = db.get(NotificationChannel, delivery.channel_id)

        if (
            channel is None
            or not channel.is_active
            or delivery.attempt_count >= MAX_ATTEMPTS
        ):
            delivery.status = "FAILED"
            delivery.last_error = (
                "channel_disabled"
                if channel is None or not channel.is_active
                else "delivery_lease_expired"
            )
            delivery.claim_token = None
            # Missing channels cannot normally survive the cascading FK. Do not
            # invent a channel label if this defensive branch encounters one.
            failed_channel_type = channel.type if channel is not None else None
        else:
            delivery.attempt_count += 1
            job = DeliveryJob(
                delivery.id,
                delivery.incident_id,
                channel.monitor_id,
                token,
                channel.type,
                channel.target,
                delivery.payload,
            )

    # Count only after the transaction context has committed successfully.
    if failed_channel_type is not None:
        NOTIFICATION_DELIVERIES.labels(
            channel_type=failed_channel_type, status="FAILED",
        ).inc()
    return job


def finish(
    sessions: SessionFactory,
    job: DeliveryJob,
    error: str | None,
    now: datetime,
) -> str | None:
    final_status: str | None = None

    with sessions() as db, db.begin():
        delivery = db.scalar(
            select(NotificationDelivery)
            .where(
                NotificationDelivery.id == job.id,
                NotificationDelivery.claim_token == job.claim_token,
                NotificationDelivery.status == "PROCESSING",
            )
            .with_for_update()
        )

        if delivery is None:
            return None

        delivery.claim_token = None
        delivery.last_error = error

        if error is None:
            delivery.status = "SENT"
            delivery.sent_at = now
        elif delivery.attempt_count >= MAX_ATTEMPTS:
            delivery.status = "FAILED"
        else:
            delivery.status = "PENDING"
            delivery.next_attempt_at = now + timedelta(
                seconds=RETRY_SECONDS[delivery.attempt_count - 1]
            )

        final_status = delivery.status

    # Keep persisted-state metrics in this thread even if its async waiter
    # is cancelled while the commit completes.
    if final_status == "PENDING":
        NOTIFICATION_DELIVERY_RETRIES.labels(channel_type=job.kind).inc()
        logger.info(
            "notification_delivery_retry_scheduled "
            "delivery_id=%s incident_id=%s monitor_id=%s",
            job.id,
            job.incident_id,
            job.monitor_id,
        )
    else:
        NOTIFICATION_DELIVERIES.labels(
            channel_type=job.kind, status=final_status,
        ).inc()
        logger.info(
            "notification_delivery_%s "
            "delivery_id=%s incident_id=%s monitor_id=%s",
            final_status.lower(),
            job.id,
            job.incident_id,
            job.monitor_id,
        )

    return final_status


async def run_delivery_cycle(
    sessions: SessionFactory,
    client: httpx.AsyncClient,
    settings: Settings,
) -> None:
    for _ in range(20):
        job = await asyncio.to_thread(
            claim_one,
            sessions,
            datetime.now(timezone.utc),
        )

        if job is None:
            break

        error = None
        outcome = "error"
        started_at = perf_counter()

        try:
            if job.kind == "EMAIL":
                await asyncio.to_thread(
                    send_email,
                    settings,
                    job.target,
                    job.payload,
                    str(job.id),
                )
            else:
                await send_webhook(
                    client,
                    job.target,
                    job.payload,
                    str(job.id),
                )

            outcome = "success"

        except asyncio.CancelledError:
            outcome = "cancelled"
            raise

        except DestinationError:
            error = "webhook_destination_blocked"

        except DeliveryError as exc:
            # DeliveryError is raised only with constants
            # from our senders.
            error = str(exc)

        except Exception:
            # SMTP/httpx exceptions may contain credentials,
            # targets or response bodies.
            error = "delivery_transport_error"

        finally:
            NOTIFICATION_DELIVERY_ATTEMPTS.labels(
                channel_type=job.kind,
                outcome=outcome,
            ).inc()

            NOTIFICATION_DELIVERY_DURATION.labels(
                channel_type=job.kind,
            ).observe(
                perf_counter() - started_at
            )

        await asyncio.to_thread(
            finish,
            sessions,
            job,
            error,
            datetime.now(timezone.utc),
        )



async def delivery_loop(
    sessions: SessionFactory,
    client: httpx.AsyncClient,
    settings: Settings,
    stop: asyncio.Event,
) -> None:
    while not stop.is_set():
        try:
            await run_delivery_cycle(
                sessions,
                client,
                settings,
            )
        except Exception:
            logger.error("notification_delivery_cycle_failed")

        try:
            await asyncio.wait_for(
                stop.wait(),
                timeout=settings.worker_poll_interval_seconds,
            )
        except TimeoutError:
            pass

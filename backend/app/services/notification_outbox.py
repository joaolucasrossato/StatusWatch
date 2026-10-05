import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Incident, Monitor, NotificationChannel, NotificationDelivery
from app.schemas.notification import DeliveryList
from app.services.notification_channels import NotificationNotFound, require_monitor


def timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc).isoformat() if value.tzinfo is None else value.isoformat()


def enqueue_transition(db: Session, incident: Incident, event_type: str) -> None:
    """Flush only: caller commits check, incident and outbox atomically."""
    db.flush()
    monitor = db.get(Monitor, incident.monitor_id)
    enabled = NotificationChannel.notify_on_open if event_type == 'INCIDENT_OPENED' else NotificationChannel.notify_on_resolved
    channels = db.scalars(select(NotificationChannel).where(
        NotificationChannel.monitor_id == incident.monitor_id,
        NotificationChannel.user_id == monitor.user_id,
        NotificationChannel.is_active.is_(True), enabled.is_(True),
    ))
    payload = {
        'event': event_type,
        'incident': {
            'id': str(incident.id), 'status': incident.status,
            'started_at': timestamp(incident.started_at), 'opened_at': timestamp(incident.opened_at),
            'resolved_at': timestamp(incident.resolved_at),
        },
        'monitor': {'id': str(monitor.id), 'name': monitor.name, 'url': monitor.url},
    }
    for channel in channels:
        db.add(NotificationDelivery(incident_id=incident.id, channel_id=channel.id, event_type=event_type, payload=payload))
    db.flush()


def delivery_page(db: Session, user_id: uuid.UUID, status: str | None, event_type: str | None,
                  monitor_id: uuid.UUID | None, incident_id: uuid.UUID | None, limit: int, offset: int) -> DeliveryList:
    filters = [Monitor.user_id == user_id]
    if monitor_id is not None:
        require_monitor(db, user_id, monitor_id)
        filters.append(Monitor.id == monitor_id)
    if incident_id is not None:
        if db.scalar(select(Incident.id).join(Monitor).where(Incident.id == incident_id, Monitor.user_id == user_id)) is None:
            raise NotificationNotFound
        filters.append(Incident.id == incident_id)
    if status is not None:
        filters.append(NotificationDelivery.status == status)
    if event_type is not None:
        filters.append(NotificationDelivery.event_type == event_type)
    statement = select(NotificationDelivery).join(Incident).join(Monitor).where(*filters)
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    items = list(db.scalars(statement.order_by(NotificationDelivery.created_at.desc(), NotificationDelivery.id.desc()).limit(limit).offset(offset)))
    return DeliveryList(items=items, total=total, limit=limit, offset=offset)

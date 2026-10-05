import asyncio
import uuid

import httpx
from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.monitor import Monitor
from app.models.notification import NotificationChannel
from app.monitoring.checker import DestinationError, destination
from app.schemas.notification import ChannelCreate, ChannelResponse, ChannelUpdate


class NotificationNotFound(Exception):
    pass


class InvalidTarget(Exception):
    pass


async def validate_target(kind: str, target: str) -> str:
    """Return normalized input; never include submitted destinations in errors."""
    try:
        if kind == "EMAIL":
            return str(TypeAdapter(EmailStr).validate_python(target))
        if any(ord(char) < 32 or ord(char) == 127 for char in target):
            raise InvalidTarget
        url = httpx.URL(target)
        if url.fragment:
            raise InvalidTarget
        async with asyncio.timeout(10):
            await destination(url)
        return str(url)
    except (ValueError, ValidationError, httpx.InvalidURL, DestinationError, TimeoutError):
        raise InvalidTarget from None


def require_monitor(db: Session, user_id: uuid.UUID, monitor_id: uuid.UUID) -> None:
    if db.scalar(select(Monitor.id).where(Monitor.id == monitor_id, Monitor.user_id == user_id)) is None:
        raise NotificationNotFound


def owned_channel(db: Session, user_id: uuid.UUID, channel_id: uuid.UUID) -> NotificationChannel:
    channel = db.scalar(select(NotificationChannel).join(Monitor).where(
        NotificationChannel.id == channel_id, NotificationChannel.user_id == user_id, Monitor.user_id == user_id,
    ))
    if channel is None:
        raise NotificationNotFound
    return channel


def list_channels(db: Session, user_id: uuid.UUID, monitor_id: uuid.UUID | None = None) -> list[NotificationChannel]:
    statement = select(NotificationChannel).join(Monitor).where(
        NotificationChannel.user_id == user_id, Monitor.user_id == user_id,
    )
    if monitor_id is not None:
        require_monitor(db, user_id, monitor_id)
        statement = statement.where(NotificationChannel.monitor_id == monitor_id)
    return list(db.scalars(statement.order_by(NotificationChannel.created_at.desc(), NotificationChannel.id.desc())))


def create_channel(db: Session, user_id: uuid.UUID, payload: ChannelCreate, target: str) -> NotificationChannel:
    require_monitor(db, user_id, payload.monitor_id)
    channel = NotificationChannel(user_id=user_id, **{**payload.model_dump(), "target": target})
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return channel


def update_channel(db: Session, channel: NotificationChannel, payload: ChannelUpdate, target: str | None) -> NotificationChannel:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(channel, field, target if field == "target" else value)
    db.commit()
    db.refresh(channel)
    return channel


def channel_response(channel: NotificationChannel) -> ChannelResponse:
    # Even URL paths can contain credentials, so expose only the origin.
    target = channel.target
    if channel.type == "WEBHOOK":
        url = httpx.URL(target)
        target = f"{url.scheme}://{url.netloc.decode('ascii')}/…"
    return ChannelResponse(
        id=channel.id, monitor_id=channel.monitor_id, type=channel.type,
        target=target, target_redacted=channel.type == "WEBHOOK",
        is_active=channel.is_active, notify_on_open=channel.notify_on_open,
        notify_on_resolved=channel.notify_on_resolved,
        created_at=channel.created_at, updated_at=channel.updated_at,
    )

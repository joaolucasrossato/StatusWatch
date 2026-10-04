import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.monitor import Monitor
from app.models.monitor_check import MonitorCheck
from app.schemas.monitor import MonitorCreate, MonitorUpdate


def create_monitor(db: Session, *, user_id: uuid.UUID, payload: MonitorCreate) -> Monitor:
    monitor = Monitor(user_id=user_id, **payload.model_dump(mode="json"))
    db.add(monitor)
    db.commit()
    db.refresh(monitor)
    return monitor


def list_monitors(db: Session, *, user_id: uuid.UUID) -> list[Monitor]:
    latest_id = select(MonitorCheck.id).where(MonitorCheck.monitor_id == Monitor.id).order_by(
        MonitorCheck.checked_at.desc(), MonitorCheck.id.desc(),
    ).limit(1).correlate(Monitor).scalar_subquery()
    rows = db.execute(select(Monitor, MonitorCheck).outerjoin(
        MonitorCheck, MonitorCheck.id == latest_id,
    ).where(Monitor.user_id == user_id).order_by(Monitor.created_at.desc(), Monitor.id.desc()))
    result = []
    for monitor, check in rows:
        monitor.latest_check = check
        result.append(monitor)
    return result


def latest_check(db: Session, monitor_id: uuid.UUID) -> MonitorCheck | None:
    return db.scalar(select(MonitorCheck).where(MonitorCheck.monitor_id == monitor_id).order_by(
        MonitorCheck.checked_at.desc(), MonitorCheck.id.desc(),
    ).limit(1))


def get_monitor(db: Session, *, user_id: uuid.UUID, monitor_id: uuid.UUID) -> Monitor:
    monitor = db.scalar(select(Monitor).where(Monitor.id == monitor_id, Monitor.user_id == user_id))
    if monitor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monitor not found")
    monitor.latest_check = latest_check(db, monitor_id)
    return monitor


def update_monitor(
    db: Session, *, user_id: uuid.UUID, monitor_id: uuid.UUID, payload: MonitorUpdate,
) -> Monitor:
    monitor = get_monitor(db, user_id=user_id, monitor_id=monitor_id)
    for field, value in payload.model_dump(mode="json", exclude_unset=True).items():
        setattr(monitor, field, value)
    db.commit()
    db.refresh(monitor)
    return monitor


def delete_monitor(db: Session, *, user_id: uuid.UUID, monitor_id: uuid.UUID) -> None:
    monitor = get_monitor(db, user_id=user_id, monitor_id=monitor_id)
    db.delete(monitor)
    db.commit()

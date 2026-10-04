import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.monitor import Monitor
from app.models.monitor_check import MonitorCheck
from app.schemas.monitor_check import MonitorCheckResponse
from app.models.user import User
from app.schemas.monitor import MonitorCreate, MonitorResponse, MonitorUpdate
from app.services import monitors

router = APIRouter(prefix="/monitors", tags=["monitors"])
Database = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.post("", response_model=MonitorResponse, status_code=status.HTTP_201_CREATED)
def create(payload: MonitorCreate, db: Database, current_user: CurrentUser) -> Monitor:
    return monitors.create_monitor(db, user_id=current_user.id, payload=payload)


@router.get("", response_model=list[MonitorResponse])
def list_all(db: Database, current_user: CurrentUser) -> list[Monitor]:
    return monitors.list_monitors(db, user_id=current_user.id)


@router.get("/{monitor_id}", response_model=MonitorResponse)
def get_one(monitor_id: uuid.UUID, db: Database, current_user: CurrentUser) -> Monitor:
    return monitors.get_monitor(db, user_id=current_user.id, monitor_id=monitor_id)


@router.patch("/{monitor_id}", response_model=MonitorResponse)
def update(monitor_id: uuid.UUID, payload: MonitorUpdate, db: Database, current_user: CurrentUser) -> Monitor:
    return monitors.update_monitor(db, user_id=current_user.id, monitor_id=monitor_id, payload=payload)


@router.delete("/{monitor_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(monitor_id: uuid.UUID, db: Database, current_user: CurrentUser) -> Response:
    monitors.delete_monitor(db, user_id=current_user.id, monitor_id=monitor_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{monitor_id}/checks/latest", response_model=MonitorCheckResponse | None)
def get_latest(monitor_id: uuid.UUID, db: Database, current_user: CurrentUser, response: Response) -> MonitorCheck | None:
    monitor = monitors.get_monitor(db, user_id=current_user.id, monitor_id=monitor_id)
    response.headers["Cache-Control"] = "no-store"
    return monitor.latest_check

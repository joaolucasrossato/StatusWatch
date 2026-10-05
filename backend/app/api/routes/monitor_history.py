import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.dashboard import (
    MonitorCheckHistoryResponse,
    MonitorStatsResponse,
)
from app.services.dashboard import (
    MonitorNotFoundError,
    get_monitor_stats,
    list_monitor_checks,
)


router = APIRouter(
    prefix="/monitors",
    tags=["monitor-history"],
)


@router.get(
    "/{monitor_id}/checks",
    response_model=MonitorCheckHistoryResponse,
)
def monitor_checks(
    monitor_id: uuid.UUID,
    response: Response,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MonitorCheckHistoryResponse:
    try:
        total, checks = list_monitor_checks(
            db,
            monitor_id=monitor_id,
            user_id=current_user.id,
            limit=limit,
            offset=offset,
        )
    except MonitorNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Monitor not found",
        ) from None

    response.headers["Cache-Control"] = "no-store"

    return MonitorCheckHistoryResponse(
        items=checks,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{monitor_id}/stats",
    response_model=MonitorStatsResponse,
)
def monitor_stats(
    monitor_id: uuid.UUID,
    response: Response,
    window_hours: int = Query(
        default=24,
        ge=1,
        le=168,
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MonitorStatsResponse:
    try:
        stats = get_monitor_stats(
            db,
            monitor_id=monitor_id,
            user_id=current_user.id,
            window_hours=window_hours,
        )
    except MonitorNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Monitor not found",
        ) from None

    response.headers["Cache-Control"] = "no-store"

    return MonitorStatsResponse(**stats)
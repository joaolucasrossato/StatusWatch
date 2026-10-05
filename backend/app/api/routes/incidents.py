from __future__ import annotations

import uuid
from typing import Literal

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Response,
    status,
)
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.incident import (
    IncidentListResponse,
    IncidentResponse,
)
from app.services.incidents import (
    IncidentNotFoundError,
    MonitorNotFoundError,
    get_owned_incident,
    list_incidents,
    list_monitor_incidents,
)


router = APIRouter(
    tags=["incidents"],
)


@router.get(
    "/incidents",
    response_model=IncidentListResponse,
)
def incidents(
    response: Response,
    incident_status: Literal["OPEN", "RESOLVED"] | None = Query(
        default=None,
        alias="status",
    ),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> IncidentListResponse:
    total, items = list_incidents(
        db,
        user_id=current_user.id,
        incident_status=incident_status,
        limit=limit,
        offset=offset,
    )

    response.headers["Cache-Control"] = "no-store"

    return IncidentListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/incidents/{incident_id}",
    response_model=IncidentResponse,
)
def incident_details(
    incident_id: uuid.UUID,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> IncidentResponse:
    try:
        incident = get_owned_incident(
            db,
            incident_id=incident_id,
            user_id=current_user.id,
        )
    except IncidentNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Incident not found",
        ) from None

    response.headers["Cache-Control"] = "no-store"

    return IncidentResponse.model_validate(incident)


@router.get(
    "/monitors/{monitor_id}/incidents",
    response_model=IncidentListResponse,
)
def monitor_incidents(
    monitor_id: uuid.UUID,
    response: Response,
    incident_status: Literal["OPEN", "RESOLVED"] | None = Query(
        default=None,
        alias="status",
    ),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> IncidentListResponse:
    try:
        total, items = list_monitor_incidents(
            db,
            monitor_id=monitor_id,
            user_id=current_user.id,
            incident_status=incident_status,
            limit=limit,
            offset=offset,
        )
    except MonitorNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Monitor not found",
        ) from None

    response.headers["Cache-Control"] = "no-store"

    return IncidentListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )
import asyncio
import uuid

from fastapi import APIRouter, Depends, Query, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.notification import ChannelCreate, ChannelResponse, ChannelUpdate, DeliveryList, DeliveryStatus, EventType
from app.services import notification_channels as channels
from app.services.notification_outbox import delivery_page


class PrivateRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request):
            try:
                response = await original(request)
            except RequestValidationError as exc:
                # Pydantic inputs may contain an entire secret-bearing webhook URL.
                response = JSONResponse(status_code=422, content={"detail": [
                    {key: item[key] for key in ("loc", "msg", "type")} for item in exc.errors()
                ]})
            except channels.NotificationNotFound:
                response = JSONResponse(status_code=404, content={"detail": "Resource not found"})
            except channels.InvalidTarget:
                response = JSONResponse(status_code=422, content={"detail": "Invalid email or public HTTP/HTTPS destination"})
            response.headers["Cache-Control"] = "no-store"
            return response
        return handler


router = APIRouter(tags=["notifications"], route_class=PrivateRoute)


@router.get("/notification-channels", response_model=list[ChannelResponse])
def channel_list(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [channels.channel_response(item) for item in channels.list_channels(db, user.id)]


@router.get("/monitors/{monitor_id}/notification-channels", response_model=list[ChannelResponse])
def monitor_channels(monitor_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [channels.channel_response(item) for item in channels.list_channels(db, user.id, monitor_id)]


@router.post("/notification-channels", response_model=ChannelResponse, status_code=201)
def channel_create(payload: ChannelCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    channels.require_monitor(db, user.id, payload.monitor_id)
    user_id = user.id
    db.rollback()  # Release the read transaction before DNS/network I/O.
    target = asyncio.run(channels.validate_target(payload.type, payload.target))
    return channels.channel_response(channels.create_channel(db, user_id, payload, target))


@router.patch("/notification-channels/{channel_id}", response_model=ChannelResponse)
def channel_update(channel_id: uuid.UUID, payload: ChannelUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    channel = channels.owned_channel(db, user.id, channel_id)
    user_id, kind = user.id, channel.type
    db.rollback()
    target = asyncio.run(channels.validate_target(kind, payload.target)) if payload.target is not None else None
    channel = channels.owned_channel(db, user_id, channel_id)
    return channels.channel_response(channels.update_channel(db, channel, payload, target))


@router.delete("/notification-channels/{channel_id}", status_code=204)
def channel_delete(channel_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    channel = channels.owned_channel(db, user.id, channel_id)
    db.delete(channel)
    db.commit()
    return Response(status_code=204)


@router.get("/notification-deliveries", response_model=DeliveryList)
def deliveries(status: DeliveryStatus | None = None, event_type: EventType | None = None,
               monitor_id: uuid.UUID | None = None, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
               db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return delivery_page(db, user.id, status, event_type, monitor_id, None, limit, offset)


@router.get("/incidents/{incident_id}/notification-deliveries", response_model=DeliveryList)
def incident_deliveries(incident_id: uuid.UUID, status: DeliveryStatus | None = None, event_type: EventType | None = None,
                        limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
                        db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return delivery_page(db, user.id, status, event_type, None, incident_id, limit, offset)

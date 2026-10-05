import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ChannelType = Literal["EMAIL", "WEBHOOK"]
EventType = Literal["INCIDENT_OPENED", "INCIDENT_RESOLVED"]
DeliveryStatus = Literal["PENDING", "PROCESSING", "SENT", "FAILED"]


class ChannelCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    monitor_id: uuid.UUID
    type: ChannelType
    target: str = Field(min_length=1, max_length=2083)
    is_active: bool = True
    notify_on_open: bool = True
    notify_on_resolved: bool = True


class ChannelUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: str | None = Field(default=None, min_length=1, max_length=2083)
    is_active: bool | None = None
    notify_on_open: bool | None = None
    notify_on_resolved: bool | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_null(cls, values: object) -> object:
        if isinstance(values, dict) and any(value is None for value in values.values()):
            raise ValueError("Channel fields cannot be null")
        return values


class ChannelResponse(BaseModel):
    id: uuid.UUID
    monitor_id: uuid.UUID
    type: ChannelType
    target: str
    target_redacted: bool
    is_active: bool
    notify_on_open: bool
    notify_on_resolved: bool
    created_at: datetime
    updated_at: datetime


class DeliveryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    incident_id: uuid.UUID
    channel_id: uuid.UUID
    event_type: EventType
    status: DeliveryStatus
    attempt_count: int
    last_error: str | None
    created_at: datetime
    sent_at: datetime | None
    next_attempt_at: datetime


class DeliveryList(BaseModel):
    items: list[DeliveryResponse]
    total: int
    limit: int
    offset: int

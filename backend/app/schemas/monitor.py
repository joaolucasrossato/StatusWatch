import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints, model_validator

MonitorName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
MonitorMethod = Literal["GET"]
MonitorInterval = Literal[30, 60, 300, 600]
MonitorTimeout = Annotated[int, Field(strict=True, ge=1, le=30)]


class MonitorCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: MonitorName
    url: HttpUrl
    method: MonitorMethod = "GET"
    interval_seconds: MonitorInterval = 60
    timeout_seconds: MonitorTimeout = 10
    is_active: bool = True


class MonitorUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: MonitorName | None = None
    url: HttpUrl | None = None
    method: MonitorMethod | None = None
    interval_seconds: MonitorInterval | None = None
    timeout_seconds: MonitorTimeout | None = None
    is_active: bool | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_null_fields(cls, values: object) -> object:
        # Omitted fields are unchanged; explicit null cannot clear required columns.
        if isinstance(values, dict) and any(value is None for value in values.values()):
            raise ValueError("Monitor fields cannot be null")
        return values


class MonitorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    url: str
    method: MonitorMethod
    interval_seconds: int
    timeout_seconds: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

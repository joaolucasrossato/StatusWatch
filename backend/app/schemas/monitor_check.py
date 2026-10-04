from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class MonitorCheckResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: Literal["UP", "DOWN"]
    http_status_code: int | None
    response_time_ms: int | None
    error_type: str | None
    error_message: str | None
    checked_at: datetime

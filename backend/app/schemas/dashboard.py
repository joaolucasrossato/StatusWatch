from __future__ import annotations

from app.schemas.monitor_check import MonitorCheckResponse

import uuid

from pydantic import BaseModel, Field


class DashboardSummaryResponse(BaseModel):
    total_monitors: int
    active_monitors: int
    paused_monitors: int
    up_monitors: int
    down_monitors: int
    pending_monitors: int
    checks_last_24h: int
    average_response_time_ms_24h: float | None


class MonitorStatsResponse(BaseModel):
    monitor_id: uuid.UUID

    window_hours: int = Field(ge=1)

    total_checks: int
    successful_checks: int
    failed_checks: int

    uptime_percentage: float | None

    average_response_time_ms: float | None
    minimum_response_time_ms: int | None
    maximum_response_time_ms: int | None

class MonitorCheckHistoryResponse(BaseModel):
    items: list[MonitorCheckResponse]
    total: int
    limit: int
    offset: int

class DashboardSummaryResponse(BaseModel):
    total_monitors: int
    active_monitors: int
    paused_monitors: int
    up_monitors: int
    down_monitors: int
    pending_monitors: int
    open_incidents: int
    checks_last_24h: int
    average_response_time_ms_24h: float | None
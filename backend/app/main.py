import logging
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Annotated

from fastapi import Depends, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from app.api.routes.auth import router as auth_router
from app.api.routes.monitors import router as monitors_router

from app.core.config import get_settings
from app.core.dependencies import Dependencies
from app.core.logging import configure_logging

from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.monitor_history import router as monitor_history_router

from app.api.routes.incidents import router as incidents_router
from app.api.routes.notifications import router as notifications_router

from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.observability.metrics import (
    API_HTTP_REQUEST_DURATION,
    API_HTTP_REQUESTS,
    API_HTTP_REQUESTS_IN_PROGRESS,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    settings = get_settings()
    logger.info("%s API starting", settings.app_name)
    dependencies = Dependencies(settings)
    app.state.dependencies = dependencies
    try:
        yield
    finally:
        dependencies.close()
        logger.info("%s API stopped", settings.app_name)


app = FastAPI(title="StatusWatch API", version="1.0.0", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(monitors_router)
app.include_router(dashboard_router)
app.include_router(monitor_history_router)
app.include_router(incidents_router)
app.include_router(notifications_router)


@app.middleware("http")
async def prometheus_http_metrics(request: Request, call_next):
    if request.url.path == "/metrics":
        return await call_next(request)

    # HTTP permits arbitrary extension methods; keep this label bounded.
    method = request.method if request.method in {
        "GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE", "CONNECT",
    } else "OTHER"
    started_at = perf_counter()

    API_HTTP_REQUESTS_IN_PROGRESS.labels(method=method).inc()

    try:
        response = await call_next(request)
    except Exception:
        route = request.scope.get("route")
        route_path = getattr(route, "path", "unmatched")

        API_HTTP_REQUESTS.labels(
            method=method,
            route=route_path,
            status_code="500",
        ).inc()

        API_HTTP_REQUEST_DURATION.labels(
            method=method,
            route=route_path,
        ).observe(perf_counter() - started_at)

        raise
    else:
        route = request.scope.get("route")
        route_path = getattr(route, "path", "unmatched")

        API_HTTP_REQUESTS.labels(
            method=method,
            route=route_path,
            status_code=str(response.status_code),
        ).inc()

        API_HTTP_REQUEST_DURATION.labels(
            method=method,
            route=route_path,
        ).observe(perf_counter() - started_at)

        return response
    finally:
        API_HTTP_REQUESTS_IN_PROGRESS.labels(method=method).dec()


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    # Never echo submitted passwords, tokens or secret-bearing URLs.
    return JSONResponse(status_code=422, content={"detail": [
        {key: item[key] for key in ("loc", "msg", "type")} for item in exc.errors()
    ]}, headers={"Cache-Control": "no-store"})


@app.exception_handler(OperationalError)
async def database_unavailable(request: Request, exc: OperationalError):
    logger.warning("database_unavailable")
    return JSONResponse(status_code=503, content={"detail": "Service temporarily unavailable"},
                        headers={"Cache-Control": "no-store"})


def get_dependencies(request: Request) -> Dependencies:
    return request.app.state.dependencies


@app.get("/")
def root() -> dict[str, str]:
    return {"name": "StatusWatch", "version": "1.0.0"}


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
        headers={"Cache-Control": "no-store"},
    )


@app.get("/health", responses={503: {"description": "Dependency unavailable"}})
def health(
    response: Response,
    dependencies: Annotated[Dependencies, Depends(get_dependencies)],
) -> dict[str, object]:
    services = dependencies.check()
    healthy = all(status == "healthy" for status in services.values())
    response.status_code = 200 if healthy else 503
    response.headers["Cache-Control"] = "no-store"
    return {
        "status": "healthy" if healthy else "unhealthy",
        "services": {"api": "healthy", **services},
    }

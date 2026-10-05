import logging
from contextlib import asynccontextmanager
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

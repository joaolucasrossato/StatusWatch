import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Request, Response

from app.api.routes.auth import router as auth_router

from app.core.config import get_settings
from app.core.dependencies import Dependencies
from app.core.logging import configure_logging

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


app = FastAPI(title="StatusWatch API", version="0.2.0", lifespan=lifespan)
app.include_router(auth_router)


def get_dependencies(request: Request) -> Dependencies:
    return request.app.state.dependencies


@app.get("/")
def root() -> dict[str, str]:
    return {"name": "StatusWatch", "version": "0.2.0"}


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

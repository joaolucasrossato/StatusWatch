import logging

from redis import Redis
from redis.backoff import NoBackoff
from redis.exceptions import RedisError
from redis.retry import Retry
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings

logger = logging.getLogger(__name__)


class Dependencies:
    """Connections shared by the API and worker, with bounded health probes."""

    def __init__(self, settings: Settings) -> None:
        self.database = create_engine(
            settings.database_url,
            pool_pre_ping=True,
            pool_timeout=3,
            connect_args={"connect_timeout": 3, "options": "-c statement_timeout=3000"},
        )
        self.redis = Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=3,
            socket_timeout=3,
            retry=Retry(NoBackoff(), 0),
        )

    def check(self) -> dict[str, str]:
        services = {"database": "healthy", "redis": "healthy"}
        try:
            with self.database.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError:
            logger.warning("PostgreSQL connection: unavailable")
            services["database"] = "unhealthy"

        try:
            if not self.redis.ping():
                services["redis"] = "unhealthy"
        except RedisError:
            logger.warning("Redis connection: unavailable")
            services["redis"] = "unhealthy"
        return services

    def close(self) -> None:
        self.redis.close()
        self.database.dispose()

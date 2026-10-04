from unittest.mock import patch

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.exc import OperationalError

from app.core.config import Settings
from app.core.dependencies import Dependencies


@pytest.mark.parametrize("database_down,redis_down", [(False, False), (True, False), (False, True), (True, True)])
def test_real_probe_logic(database_down, redis_down):
    with patch("app.core.dependencies.create_engine") as engine, patch("app.core.dependencies.Redis.from_url") as redis:
        connections = Dependencies(Settings(database_url="postgresql+psycopg://example", redis_url="redis://example"))
        connection = engine.return_value.connect.return_value.__enter__.return_value
        if database_down:
            engine.return_value.connect.side_effect = OperationalError("SELECT 1", {}, Exception())
        if redis_down:
            redis.return_value.ping.side_effect = RedisConnectionError()
        else:
            redis.return_value.ping.return_value = True

        assert connections.check() == {
            "database": "unhealthy" if database_down else "healthy",
            "redis": "unhealthy" if redis_down else "healthy",
        }
        redis.return_value.ping.assert_called_once()
        if not database_down:
            assert str(connection.execute.call_args.args[0]) == "SELECT 1"
        connections.close()
        redis.return_value.close.assert_called_once()
        engine.return_value.dispose.assert_called_once()

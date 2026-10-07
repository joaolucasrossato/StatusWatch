import asyncio
import signal
from unittest.mock import AsyncMock, Mock, call, patch

import pytest

from app.core.config import Settings
from app.worker import main


@pytest.mark.parametrize("shutdown_signal", [signal.SIGTERM, signal.SIGINT])
def test_worker_clean_shutdown(shutdown_signal):
    handlers = {}

    async def scheduler(*args):
        handlers[shutdown_signal]()
        await asyncio.Event().wait()

    async def idle_loop(*args):
        await asyncio.Event().wait()

    metrics_server = Mock()
    metrics_thread = Mock()

    with (
        patch("app.worker.Dependencies") as factory,
        patch(
            "asyncio.unix_events._UnixSelectorEventLoop.add_signal_handler",
            side_effect=lambda sig, callback: handlers.update({sig: callback}),
        ),
        patch(
            "asyncio.unix_events._UnixSelectorEventLoop.remove_signal_handler"
        ),
        patch(
            "app.worker.scheduler_loop",
            side_effect=scheduler,
        ),
        patch(
            "app.worker.delivery_loop",
            side_effect=idle_loop,
        ),
        patch(
            "app.worker.cleanup_loop",
            side_effect=idle_loop,
        ),
        patch(
            "app.worker.start_http_server",
            return_value=(metrics_server, metrics_thread),
        ) as start_metrics,
    ):
        factory.return_value.check.return_value = {
            "database": "healthy",
            "redis": "healthy",
        }

        lifecycle = Mock()
        lifecycle.attach_mock(start_metrics, "start")
        lifecycle.attach_mock(metrics_server.shutdown, "shutdown")
        lifecycle.attach_mock(metrics_server.server_close, "server_close")
        lifecycle.attach_mock(metrics_thread.join, "join")
        lifecycle.attach_mock(factory.return_value.close, "close")

        assert main() == 0
        assert lifecycle.mock_calls == [
            call.start(Settings().worker_metrics_port, addr="0.0.0.0"),
            call.shutdown(), call.server_close(), call.join(timeout=5), call.close(),
        ]

        start_metrics.assert_called_once()

        metrics_server.shutdown.assert_called_once()
        metrics_server.server_close.assert_called_once()
        metrics_thread.join.assert_called_once_with(timeout=5)

        factory.return_value.close.assert_called_once()


def test_worker_fails_when_dependency_unavailable():
    with (
        patch("app.worker.Dependencies") as factory,
        patch(
            "app.worker.scheduler_loop",
            new_callable=AsyncMock,
        ) as scheduler,
        patch(
            "app.worker.start_http_server",
        ) as start_metrics,
    ):
        factory.return_value.check.return_value = {
            "database": "unhealthy",
            "redis": "healthy",
        }

        assert main() == 1

        scheduler.assert_not_called()
        start_metrics.assert_not_called()
        factory.return_value.close.assert_called_once()


@pytest.mark.parametrize(
    "field,value",
    [
        ("worker_max_concurrency", 0),
        ("worker_max_concurrency", 101),
        ("worker_poll_interval_seconds", 0),
        ("worker_max_redirects", -1),
        ("worker_metrics_port", 1023),
        ("worker_metrics_port", 65536),
    ],
)
def test_invalid_worker_configuration(field, value):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(**{field: value})


def test_metrics_start_failure_closes_dependencies():
    with (
        patch('app.worker.Dependencies') as factory,
        patch('app.worker.start_http_server', side_effect=OSError('port in use')),
        patch('app.worker.scheduler_loop', new_callable=AsyncMock) as scheduler,
    ):
        factory.return_value.check.return_value = {'database': 'healthy', 'redis': 'healthy'}
        with pytest.raises(OSError, match='port in use'):
            main()
        scheduler.assert_not_called()
        factory.return_value.close.assert_called_once()

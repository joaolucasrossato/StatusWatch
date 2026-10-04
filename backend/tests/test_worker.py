import asyncio
import signal
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import Settings
from app.worker import main


@pytest.mark.parametrize("shutdown_signal", [signal.SIGTERM, signal.SIGINT])
def test_worker_clean_shutdown(shutdown_signal):
    handlers = {}
    async def scheduler(*args):
        handlers[shutdown_signal]()
        await asyncio.Event().wait()
    with patch('app.worker.Dependencies') as factory, \
         patch('asyncio.unix_events._UnixSelectorEventLoop.add_signal_handler', side_effect=lambda sig, callback: handlers.update({sig: callback})), \
         patch('asyncio.unix_events._UnixSelectorEventLoop.remove_signal_handler'), \
         patch('app.worker.scheduler_loop', side_effect=scheduler):
        factory.return_value.check.return_value = {'database': 'healthy', 'redis': 'healthy'}
        assert main() == 0
        factory.return_value.close.assert_called_once()


def test_worker_fails_when_dependency_unavailable():
    with patch('app.worker.Dependencies') as factory, patch('app.worker.scheduler_loop', new_callable=AsyncMock) as scheduler:
        factory.return_value.check.return_value = {'database': 'unhealthy', 'redis': 'healthy'}
        assert main() == 1
        scheduler.assert_not_called()
        factory.return_value.close.assert_called_once()


@pytest.mark.parametrize('field,value', [('worker_max_concurrency', 0), ('worker_max_concurrency', 101),
    ('worker_poll_interval_seconds', 0), ('worker_max_redirects', -1)])
def test_invalid_worker_configuration(field, value):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Settings(**{field: value})

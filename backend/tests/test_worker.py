import signal
from unittest.mock import patch

import pytest

from app.worker import main


@pytest.mark.parametrize("shutdown_signal", [signal.SIGTERM, signal.SIGINT])
def test_worker_clean_shutdown(shutdown_signal):
    with patch("app.worker.Dependencies") as factory, patch("app.worker.get_settings"), patch("app.worker.signal.signal") as register, patch("app.worker.Event") as event:
        factory.return_value.check.return_value = {"database": "healthy", "redis": "healthy"}
        def stop_on_wait():
            handlers = dict(call.args for call in register.call_args_list)
            handlers[shutdown_signal](shutdown_signal, None)
        event.return_value.wait.side_effect = stop_on_wait
        assert main() == 0
        event.return_value.set.assert_called_once()
        factory.return_value.close.assert_called_once()


def test_worker_fails_when_dependency_unavailable():
    with patch("app.worker.Dependencies") as factory, patch("app.worker.get_settings"), patch("app.worker.signal.signal"), patch("app.worker.Event") as event:
        factory.return_value.check.return_value = {"database": "unhealthy", "redis": "healthy"}
        assert main() == 1
        event.return_value.wait.assert_not_called()
        factory.return_value.close.assert_called_once()

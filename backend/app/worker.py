import logging
import signal
from threading import Event

from app.core.config import get_settings
from app.core.dependencies import Dependencies
from app.core.logging import configure_logging

logger = logging.getLogger(__name__)


def main() -> int:
    configure_logging()
    stop = Event()

    def request_shutdown(signum: int, _frame: object) -> None:
        logger.info("Shutdown requested (signal %s)", signum)
        stop.set()

    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)
    logger.info("StatusWatch Worker starting...")
    dependencies = Dependencies(get_settings())
    try:
        services = dependencies.check()
        for name, status in services.items():
            label = "PostgreSQL" if name == "database" else "Redis"
            logger.info("%s connection: %s", label, "OK" if status == "healthy" else "FAILED")
        if any(status != "healthy" for status in services.values()):
            logger.error("Worker cannot start: dependencies unavailable")
            return 1
        logger.info("StatusWatch Worker ready.")
        stop.wait()
        return 0
    finally:
        dependencies.close()
        logger.info("StatusWatch Worker stopped.")


if __name__ == "__main__":
    raise SystemExit(main())

import asyncio
import logging
import signal

from prometheus_client import start_http_server
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.dependencies import Dependencies
from app.core.logging import configure_logging
from app.monitoring.checker import create_client
from app.monitoring.scheduler import scheduler_loop
from app.notifications.worker import delivery_loop
from app.services.retention import cleanup_loop

logger = logging.getLogger(__name__)


async def run_worker() -> int:
    settings = get_settings()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    dependencies = Dependencies(settings)

    metrics_server = None
    metrics_thread = None

    try:
        services = await asyncio.to_thread(dependencies.check)
        for name, status in services.items():
            logger.info("%s connection: %s", name, status)
        if any(status != "healthy" for status in services.values()):
            logger.error("Worker cannot start: dependencies unavailable")
            return 1

        metrics_server, metrics_thread = start_http_server(
            settings.worker_metrics_port,
            addr="0.0.0.0",
        )

        logger.info(
            "Worker metrics server listening on port %s",
            settings.worker_metrics_port,
        )

        sessions = sessionmaker(bind=dependencies.database, expire_on_commit=False)
        async with create_client(settings.worker_max_concurrency) as client:
            logger.info("StatusWatch Worker ready.")
            scheduler = asyncio.create_task(scheduler_loop(
                sessions, client, stop, settings.worker_max_concurrency,
                settings.worker_poll_interval_seconds, settings.worker_max_redirects,
            ))
            deliveries = asyncio.create_task(delivery_loop(sessions, client, settings, stop))
            retention = asyncio.create_task(cleanup_loop(sessions, settings, stop))
            shutdown = asyncio.create_task(stop.wait())
            try:
                await asyncio.wait((scheduler, deliveries, retention, shutdown), return_when=asyncio.FIRST_COMPLETED)
                if retention.done():
                    await retention
                if deliveries.done():
                    await deliveries
                if scheduler.done():
                    await scheduler
            finally:
                retention.cancel()
                deliveries.cancel()
                scheduler.cancel()
                shutdown.cancel()
                await asyncio.gather(scheduler, deliveries, retention, shutdown, return_exceptions=True)
        return 0
    finally:
        if metrics_server is not None:
            await asyncio.to_thread(metrics_server.shutdown)
            await asyncio.to_thread(metrics_server.server_close)

        if metrics_thread is not None:
            await asyncio.to_thread(metrics_thread.join, timeout=5)
        await asyncio.to_thread(dependencies.close)
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.remove_signal_handler(sig)
        logger.info("StatusWatch Worker stopped.")


def main() -> int:
    configure_logging()
    # httpx INFO logs include full URLs. Never log monitored URL/query values.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    return asyncio.run(run_worker())


if __name__ == "__main__":
    raise SystemExit(main())

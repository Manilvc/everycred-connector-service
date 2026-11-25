"""Background worker: delivers queued events to the holder service.

Run one instance per deployment::

    python -m app.worker

Every ``WORKER_INTERVAL_SECONDS`` it sends the outbox rows that are due,
retrying failures with backoff. After each successful round it touches
:data:`HEARTBEAT_FILE`; ``python -m app.worker --check`` exits non-zero
when the file is older than :data:`HEARTBEAT_MAX_AGE_SECONDS`, which the
container health check uses.

Rows are not locked between processes, so two workers could send an
event twice. The holder service treats ``X-EveryCRED-Delivery`` as an
idempotency key, as a retry after a lost response can repeat one anyway.
"""

import asyncio
import logging
import signal
import sys
import tempfile
import time
from contextlib import suppress
from pathlib import Path

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.core.database import create_database_engine, create_session_factory
from app.core.http_client import create_http_client
from app.core.logging import configure_logging
from app.core.telemetry import configure_telemetry, shutdown_telemetry, span
from app.features.notifications.service import NotificationService

logger = logging.getLogger("app.worker")

BATCH_SIZE = 50
# /tmp is the only writable path in the read-only container.
HEARTBEAT_FILE = Path(tempfile.gettempdir()) / "everycred-connector-heartbeat"
HEARTBEAT_MAX_AGE_SECONDS = 120

TELEMETRY_SERVICE_NAME = "everycred-connector-worker"
DELIVER_JOB_SPAN = "holder_notification.deliver_due"
BATCH_SIZE_ATTRIBUTE = "everycred.worker.batch_size"
PROCESSED_ATTRIBUTE = "everycred.worker.processed"


async def run_once(
    session_factory: async_sessionmaker[AsyncSession],
    http_client: httpx.AsyncClient,
    settings: Settings,
) -> int:
    """Deliver one batch of due notifications; return how many succeeded.

    The batch runs in one span. A failure records the error on it and
    re-raises, so the round still logs it as failed.
    """
    async with session_factory() as session:
        notifications = NotificationService(session, http_client, settings)
        with span(
            DELIVER_JOB_SPAN,
            attributes={BATCH_SIZE_ATTRIBUTE: BATCH_SIZE},
        ) as job:
            delivered = await notifications.deliver_due(BATCH_SIZE)
            job.set_attribute(PROCESSED_ATTRIBUTE, delivered)
    return delivered


async def run_forever(stop: asyncio.Event) -> None:
    """Loop until ``stop`` is set, logging (not raising) failed rounds."""
    settings = get_settings()
    engine = create_database_engine(settings)
    # The engine is created first because configure_telemetry() traces
    # the engines it is given; an engine created later would be missed.
    # A no-op unless OTEL_EXPORTER_OTLP_ENDPOINT is set.
    telemetry = configure_telemetry(
        TELEMETRY_SERVICE_NAME,
        service_version=settings.service_version,
        engines=[engine],
    )
    session_factory = create_session_factory(engine)
    http_client = create_http_client(settings)
    if settings.holder_service_webhook_url is None:
        logger.warning(
            "HOLDER_SERVICE_WEBHOOK_URL is not set; nothing will be sent"
        )
    logger.info(
        "Worker started; running every %s s", settings.worker_interval_seconds
    )
    try:
        while not stop.is_set():
            try:
                delivered = await run_once(
                    session_factory, http_client, settings
                )
                HEARTBEAT_FILE.touch()
                if delivered:
                    logger.info("Delivered %d notification(s)", delivered)
            except Exception:
                # A database or network blip must not kill the worker;
                # the next round tries again.
                logger.exception("Worker round failed")
            with suppress(TimeoutError):
                await asyncio.wait_for(
                    stop.wait(), timeout=settings.worker_interval_seconds
                )
    finally:
        await http_client.aclose()
        await engine.dispose()
        shutdown_telemetry(telemetry)
        logger.info("Worker stopped")


def is_healthy(now: float | None = None) -> bool:
    """Return True if a round succeeded within the allowed age."""
    try:
        last_round = HEARTBEAT_FILE.stat().st_mtime
    except FileNotFoundError:
        return False
    current = time.time() if now is None else now
    return current - last_round <= HEARTBEAT_MAX_AGE_SECONDS


def main() -> None:
    """Entry point: configure logging and stop cleanly on SIGTERM.

    With ``--check``, exit 0 or 1 by :func:`is_healthy` instead.
    """
    if "--check" in sys.argv[1:]:
        sys.exit(0 if is_healthy() else 1)
    settings = get_settings()
    configure_logging(settings.log_level, use_json=settings.log_json)

    async def runner() -> None:
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for signal_number in (signal.SIGINT, signal.SIGTERM):
            # Not supported on Windows event loops; Ctrl+C still works
            # there through KeyboardInterrupt.
            with suppress(NotImplementedError):
                loop.add_signal_handler(signal_number, stop.set)
        await run_forever(stop)

    with suppress(KeyboardInterrupt):
        asyncio.run(runner())


if __name__ == "__main__":
    main()

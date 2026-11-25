"""Telemetry for the background worker process in ``app/worker.py``."""

import asyncio
import logging
from typing import Any

import httpx
import pytest
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.trace import (
    SpanKind,
    StatusCode,
    format_span_id,
    format_trace_id,
)
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from app import worker
from app.core.config import get_settings
from app.core.telemetry import bootstrap
from app.features.notifications.service import NotificationService
from tests.conftest import TelemetryCapture

ENDPOINT_VARIABLE = "OTEL_EXPORTER_OTLP_ENDPOINT"


def _job_spans(
    exporter: InMemorySpanExporter, name: str
) -> list[ReadableSpan]:
    return [
        finished
        for finished in exporter.get_finished_spans()
        if finished.name == name
    ]


def _accepting_holder(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"status": "accepted"})


async def test_round_runs_the_delivery_job_in_a_span(
    session_factory: async_sessionmaker[AsyncSession],
    telemetry: TelemetryCapture,
) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_accepting_holder)
    ) as http_client:
        delivered = await worker.run_once(
            session_factory, http_client, get_settings()
        )

    assert delivered == 0
    [job] = _job_spans(telemetry.spans, worker.DELIVER_JOB_SPAN)
    assert job.kind is SpanKind.INTERNAL
    assert job.status.status_code is not StatusCode.ERROR
    assert job.attributes[worker.BATCH_SIZE_ATTRIBUTE] == worker.BATCH_SIZE
    assert job.attributes[worker.PROCESSED_ATTRIBUTE] == 0


async def test_job_counts_the_notifications_it_delivered(
    session_factory: async_sessionmaker[AsyncSession],
    telemetry: TelemetryCapture,
) -> None:
    async with session_factory() as session:
        service = NotificationService(
            session,
            httpx.AsyncClient(
                transport=httpx.MockTransport(_accepting_holder)
            ),
            get_settings(),
        )
        service.enqueue("credential.issued", {"credential_id": "cred-1"})
        await session.commit()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_accepting_holder)
    ) as http_client:
        delivered = await worker.run_once(
            session_factory, http_client, get_settings()
        )

    assert delivered == 1
    [job] = _job_spans(telemetry.spans, worker.DELIVER_JOB_SPAN)
    assert job.attributes[worker.PROCESSED_ATTRIBUTE] == 1


async def test_failing_job_records_the_error_and_re_raises(
    session_factory: async_sessionmaker[AsyncSession],
    telemetry: TelemetryCapture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def broken_delivery(self: Any, batch_size: int) -> int:
        raise RuntimeError("database went away")

    monkeypatch.setattr(NotificationService, "deliver_due", broken_delivery)

    async with httpx.AsyncClient() as http_client:
        with pytest.raises(RuntimeError, match="database went away"):
            await worker.run_once(session_factory, http_client, get_settings())

    [job] = _job_spans(telemetry.spans, worker.DELIVER_JOB_SPAN)
    assert job.status.status_code is StatusCode.ERROR
    assert job.status.description == "RuntimeError"
    assert [event.name for event in job.events] == ["exception"]


async def test_log_line_inside_the_job_carries_its_span_ids(
    session_factory: async_sessionmaker[AsyncSession],
    telemetry: TelemetryCapture,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def logging_delivery(self: Any, batch_size: int) -> int:
        logging.getLogger("app.worker").info("Delivering inside the job")
        return 0

    monkeypatch.setattr(NotificationService, "deliver_due", logging_delivery)

    async with httpx.AsyncClient() as http_client:
        with caplog.at_level(logging.INFO, logger="app.worker"):
            await worker.run_once(session_factory, http_client, get_settings())

    [job] = _job_spans(telemetry.spans, worker.DELIVER_JOB_SPAN)
    [record] = [
        record
        for record in caplog.records
        if record.getMessage() == "Delivering inside the job"
    ]
    assert record.trace_id == format_trace_id(job.context.trace_id)
    assert record.span_id == format_span_id(job.context.span_id)


async def test_run_forever_starts_telemetry_as_the_worker_and_stops_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    providers = object()
    started: list[tuple[str, dict[str, Any]]] = []
    stopped: list[object] = []

    def fake_configure(service_name: str, **kwargs: Any) -> object:
        started.append((service_name, kwargs))
        return providers

    monkeypatch.setattr(worker, "configure_telemetry", fake_configure)
    monkeypatch.setattr(worker, "shutdown_telemetry", stopped.append)
    # A set stop event is the state a SIGTERM leaves the loop in, so this
    # run takes the same exit path, through the finally block.
    stop = asyncio.Event()
    stop.set()

    await worker.run_forever(stop)

    [(service_name, kwargs)] = started
    assert service_name == "everycred-connector-worker"
    [engine] = kwargs["engines"]
    assert isinstance(engine, AsyncEngine)
    assert stopped == [providers]


async def test_no_endpoint_starts_no_exporter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ENDPOINT_VARIABLE, "")

    def refuse_exporter(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("an exporter was created without an endpoint")

    monkeypatch.setattr(bootstrap, "OTLPSpanExporter", refuse_exporter)
    monkeypatch.setattr(bootstrap, "OTLPMetricExporter", refuse_exporter)
    stop = asyncio.Event()
    stop.set()

    await worker.run_forever(stop)

import json
import logging
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.trace import SpanKind, StatusCode, format_trace_id
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.core.logging import JsonFormatter
from app.core.telemetry import instrument_app
from app.core.telemetry.engines import create_traced_async_engine
from app.main import create_app
from tests.conftest import (
    ADMIN_HEADERS,
    FakeSources,
    TelemetryCapture,
    register_client,
    register_source,
)
from tests.helpers import build_event, send_event

ENDPOINT_VARIABLE = "OTEL_EXPORTER_OTLP_ENDPOINT"
SQLALCHEMY_SCOPE = "opentelemetry.instrumentation.sqlalchemy"
OPERATIONS_METRIC = "everycred.holder.operations"
HOLDER_EMAIL = "holder@example.com"


@pytest.fixture
async def session_factory(
    telemetry: TelemetryCapture,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    # The engine is created after instrumentation started, as a
    # per-tenant engine would be, so it goes through the traced factory.
    engine = create_traced_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
def outbound_client(
    outbound_client: httpx.AsyncClient,
) -> httpx.AsyncClient:
    # Production relies on the patch of httpx.AsyncHTTPTransport, which
    # MockTransport bypasses, so the test client is instrumented itself.
    HTTPXClientInstrumentor.instrument_client(outbound_client)
    return outbound_client


@pytest.fixture
def app(
    app: FastAPI,
    telemetry: TelemetryCapture,
    monkeypatch: pytest.MonkeyPatch,
) -> FastAPI:
    # instrument_app() acts only when an endpoint is set. It is cleared
    # again before the lifespan runs so no real exporter starts.
    monkeypatch.setenv(ENDPOINT_VARIABLE, "http://collector.test:4318")
    instrument_app(app)
    monkeypatch.setenv(ENDPOINT_VARIABLE, "")
    return app


@pytest.fixture
async def holder_headers(client: AsyncClient) -> dict[str, str]:
    headers = await register_client(client, "holder_service")
    secret = await register_source(client, "dcs-india")
    response = await send_event(
        client,
        "dcs-india",
        secret,
        build_event(
            "request.created", request_id="req-1", holder_email=HOLDER_EMAIL
        ),
    )
    assert response.status_code == 202
    return headers


def _spans_named(telemetry: TelemetryCapture, name: str) -> list[ReadableSpan]:
    return [
        finished
        for finished in telemetry.spans.get_finished_spans()
        if finished.name == name
    ]


async def _run_operation(
    client: AsyncClient, headers: dict[str, str], operation: str
) -> httpx.Response:
    return await client.post(
        "/v1/holders/operations",
        json={
            "holder_email": HOLDER_EMAIL,
            "operation": operation,
            "source_code": "dcs-india",
            "params": {"request_id": "req-1"},
        },
        headers=headers,
    )


def _dcs_ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"status": "success", "data": {}})


def test_create_app_adds_tracing_only_with_an_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert not isinstance(
        create_app().build_middleware_stack().app, OpenTelemetryMiddleware
    )

    monkeypatch.setenv(ENDPOINT_VARIABLE, "http://collector.test:4318")

    assert isinstance(
        create_app().build_middleware_stack().app, OpenTelemetryMiddleware
    )


async def test_request_creates_server_span_with_query_children(
    client: AsyncClient, telemetry: TelemetryCapture
) -> None:
    response = await client.get("/v1/sources", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    [server] = _spans_named(telemetry, "GET /v1/sources")
    assert server.kind is SpanKind.SERVER
    queries = [
        finished
        for finished in telemetry.spans.get_finished_spans()
        if finished.instrumentation_scope.name == SQLALCHEMY_SCOPE
        and finished.context.trace_id == server.context.trace_id
    ]
    assert queries
    assert all(query.kind is SpanKind.CLIENT for query in queries)


async def test_operation_records_span_metric_and_traceparent(
    client: AsyncClient,
    holder_headers: dict[str, str],
    fake_sources: FakeSources,
    telemetry: TelemetryCapture,
) -> None:
    fake_sources.handle("dcs-india.example.com", _dcs_ok)
    telemetry.metrics.get_metrics_data()

    response = await _run_operation(client, holder_headers, "requests.get")

    assert response.status_code == 200
    [server] = _spans_named(telemetry, "POST /v1/holders/operations")
    [operation] = _spans_named(telemetry, "connector.operation")
    assert operation.context.trace_id == server.context.trace_id
    assert operation.attributes["everycred.operation"] == "requests.get"
    assert operation.attributes["everycred.result"] == "ok"
    traceparent = fake_sources.requests[-1].headers["traceparent"]
    assert traceparent.split("-")[1] == format_trace_id(
        server.context.trace_id
    )
    assert telemetry.counter_points(OPERATIONS_METRIC) == [
        {"operation": "requests.get", "result": "ok", "value": 1}
    ]


async def test_unknown_operation_is_counted_without_its_name(
    client: AsyncClient,
    holder_headers: dict[str, str],
    telemetry: TelemetryCapture,
) -> None:
    telemetry.metrics.get_metrics_data()

    response = await _run_operation(client, holder_headers, "made.up")

    assert response.status_code == 400
    [operation] = _spans_named(telemetry, "connector.operation")
    assert operation.status.status_code is StatusCode.ERROR
    assert operation.attributes["everycred.operation"] == "unknown"
    assert telemetry.counter_points(OPERATIONS_METRIC) == [
        {"operation": "unknown", "result": "rejected", "value": 1}
    ]


async def test_failing_source_is_counted_as_failed(
    client: AsyncClient,
    holder_headers: dict[str, str],
    telemetry: TelemetryCapture,
) -> None:
    telemetry.metrics.get_metrics_data()

    # No handler is registered, so the fake source refuses to connect.
    await _run_operation(client, holder_headers, "requests.get")

    [operation] = _spans_named(telemetry, "connector.operation")
    assert operation.attributes["everycred.result"] == "failed"
    assert telemetry.counter_points(OPERATIONS_METRIC) == [
        {"operation": "requests.get", "result": "failed", "value": 1}
    ]


async def test_spans_never_carry_the_holder_email(
    client: AsyncClient,
    holder_headers: dict[str, str],
    fake_sources: FakeSources,
    telemetry: TelemetryCapture,
) -> None:
    fake_sources.handle("dcs-india.example.com", _dcs_ok)

    await _run_operation(client, holder_headers, "requests.get")

    assert fake_sources.requests[-1].headers["X-Holder-Email"] == HOLDER_EMAIL
    recorded = [
        f"{key}={value}".lower()
        for finished in telemetry.spans.get_finished_spans()
        for key, value in (finished.attributes or {}).items()
    ]
    assert recorded
    assert not [item for item in recorded if HOLDER_EMAIL in item]
    assert not [item for item in recorded if "holder-email" in item]
    assert not [item for item in recorded if "x-api-key" in item]


async def test_request_log_line_carries_the_trace_id(
    client: AsyncClient,
    telemetry: TelemetryCapture,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="app.core.middleware"):
        await client.get("/v1/sources", headers=ADMIN_HEADERS)

    [server] = _spans_named(telemetry, "GET /v1/sources")
    [record] = [
        record
        for record in caplog.records
        if record.name == "app.core.middleware"
    ]
    trace_id = format_trace_id(server.context.trace_id)
    assert record.trace_id == trace_id
    assert json.loads(JsonFormatter().format(record))["trace_id"] == trace_id

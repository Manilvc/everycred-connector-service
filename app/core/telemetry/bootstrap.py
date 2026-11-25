"""Start and stop OpenTelemetry for one service process.

Two entry points, because they must run at different moments:

* ``instrument_app()`` runs when the FastAPI app is created. Starlette
  builds its middleware stack before the lifespan starts, so the
  tracing middleware has to be attached first. It starts no threads
  and only talks to the global (proxy) providers.
* ``configure_telemetry()`` runs inside each worker process: in the
  FastAPI lifespan, or in Celery's ``worker_process_init`` signal. The
  batch exporters start background threads, and threads do not survive
  a fork, so creating them before gunicorn or Celery forks would lose
  every span silently.

Exporters use OTLP over HTTP. It needs no native gRPC library and has
none of gRPC's fork-safety caveats, which matters for Celery prefork.

All settings come from the standard ``OTEL_*`` environment variables
read by the SDK itself (endpoint, sampler, resource attributes), so
every service is configured the same way.
"""

# fmt: off
# isort: skip_file

import logging
import os
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
    OTLPMetricExporter,
)
from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from .logs import install_log_correlation
from .redaction import RedactingSpanExporter

# Instrumentation packages are optional: each service installs only the
# ones for the libraries it uses, and the rest are skipped.
try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
except ImportError:
    FastAPIInstrumentor = None
try:
    from opentelemetry.instrumentation.sqlalchemy import (
        SQLAlchemyInstrumentor,
    )
except ImportError:
    SQLAlchemyInstrumentor = None
try:
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
except ImportError:
    HTTPXClientInstrumentor = None
try:
    from opentelemetry.instrumentation.aiohttp_client import (
        AioHttpClientInstrumentor,
    )
except ImportError:
    AioHttpClientInstrumentor = None
try:
    from opentelemetry.instrumentation.requests import RequestsInstrumentor
except ImportError:
    RequestsInstrumentor = None
try:
    from opentelemetry.instrumentation.redis import RedisInstrumentor
except ImportError:
    RedisInstrumentor = None
try:
    from opentelemetry.instrumentation.celery import CeleryInstrumentor
except ImportError:
    CeleryInstrumentor = None
try:
    from opentelemetry.instrumentation.system_metrics import (
        SystemMetricsInstrumentor,
    )
except ImportError:
    SystemMetricsInstrumentor = None

logger = logging.getLogger(__name__)

SERVICE_NAMESPACE = "everycred"
# Health checks, metrics scrapes and API docs would otherwise dominate
# trace volume without telling anyone anything.
DEFAULT_EXCLUDED_URLS = "health,healthz,ready,metrics,docs,redoc,openapi.json"
_TRUE_VALUES = {"1", "true", "yes", "on"}
_ENDPOINT_VARIABLES = (
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
)

_active: "TelemetryProviders | None" = None


@dataclass(frozen=True)
class TelemetryProviders:
    """Providers installed for this process, kept for shutdown.

    Attributes:
        tracer_provider: Global tracer provider set by this package.
        meter_provider: Global meter provider set by this package.
    """

    tracer_provider: TracerProvider
    meter_provider: MeterProvider


def is_telemetry_enabled() -> bool:
    """Return True when an OTLP endpoint is set and the SDK is not off.

    Reads the standard ``OTEL_SDK_DISABLED`` and
    ``OTEL_EXPORTER_OTLP_ENDPOINT`` variables. Without an endpoint the
    SDK would export to localhost and log a connection error for every
    batch, so a service with no collector settings stays fully off.
    """
    if os.environ.get("OTEL_SDK_DISABLED", "").lower() in _TRUE_VALUES:
        return False
    return any(os.environ.get(name) for name in _ENDPOINT_VARIABLES)


def instrument_app(
    app: Any, excluded_urls: str = DEFAULT_EXCLUDED_URLS
) -> None:
    """Attach server tracing to a FastAPI app; call at app creation.

    Request and response headers are never captured: header capture
    stays off unless ``OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_*`` is
    set, and services must not set it.

    Args:
        app: The FastAPI application.
        excluded_urls: Comma-separated path patterns to skip.
    """
    if not is_telemetry_enabled() or FastAPIInstrumentor is None:
        return
    FastAPIInstrumentor.instrument_app(
        app,
        excluded_urls=excluded_urls,
        # The per-message receive/send spans add noise, not insight.
        exclude_spans=["receive", "send"],
    )


def _build_resource(
    service_name: str, service_version: str | None
) -> Resource:
    attributes = {
        "service.name": service_name,
        "service.namespace": SERVICE_NAMESPACE,
    }
    if service_version:
        attributes["service.version"] = service_version
    # Resource.create merges OTEL_RESOURCE_ATTRIBUTES (for example
    # deployment.environment) underneath these code-defined values.
    return Resource.create(attributes)


def _instrument_libraries(engines: Iterable[Any], celery: bool) -> None:
    if SQLAlchemyInstrumentor is not None:
        # Passing existing engines instruments them now. Engines created
        # later are traced only when made through the patched factory,
        # i.e. via engines.create_traced_async_engine().
        sync_engines = [getattr(e, "sync_engine", e) for e in engines]
        # The 0.60b1 instrumentation declares sqlalchemy < 2.1, but works
        # on 2.1 (holder, connector and integration services use it).
        # Without skipping the check it logs DependencyConflict and
        # silently records no DB spans.
        SQLAlchemyInstrumentor().instrument(
            engines=sync_engines, skip_dep_check=True
        )
    for instrumentor in (
        HTTPXClientInstrumentor,
        AioHttpClientInstrumentor,
        RequestsInstrumentor,
        RedisInstrumentor,
        SystemMetricsInstrumentor,
    ):
        if instrumentor is not None:
            instrumentor().instrument()
    if celery and CeleryInstrumentor is not None:
        CeleryInstrumentor().instrument()


def configure_telemetry(
    service_name: str,
    *,
    service_version: str | None = None,
    engines: Iterable[Any] = (),
    celery: bool = False,
) -> TelemetryProviders | None:
    """Install tracing, metrics and log correlation for this process.

    Idempotent: a second call returns None and changes nothing.

    Args:
        service_name: ``service.name`` shown in Grafana, e.g.
            ``"everycred-dcs-api"``.
        service_version: Build or release identifier, if known.
        engines: SQLAlchemy engines (sync or async) created before this
            call, such as module-level engines.
        celery: True inside a Celery worker or beat process.

    Returns:
        The installed providers, to pass to ``shutdown_telemetry()``,
        or None when telemetry is disabled or already configured.
    """
    global _active
    install_log_correlation()
    if _active is not None or not is_telemetry_enabled():
        return None

    resource = _build_resource(service_name, service_version)
    # TracerProvider reads OTEL_TRACES_SAMPLER / _ARG itself; the
    # default is parent-based always-on, which suits dev and staging.
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(RedactingSpanExporter(OTLPSpanExporter()))
    )
    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())],
    )
    trace.set_tracer_provider(tracer_provider)
    metrics.set_meter_provider(meter_provider)
    _instrument_libraries(engines, celery)

    _active = TelemetryProviders(tracer_provider, meter_provider)
    logger.info("Telemetry started for %s", service_name)
    return _active


def shutdown_telemetry(providers: TelemetryProviders | None) -> None:
    """Flush queued spans and metrics, then stop the exporters.

    Args:
        providers: Value returned by ``configure_telemetry()``; None is
            accepted so callers need no check of their own.
    """
    global _active
    if providers is None:
        return
    # Each provider flushes before it stops, so the last requests of a
    # shutting-down worker still reach the collector.
    providers.tracer_provider.shutdown()
    providers.meter_provider.shutdown()
    _active = None

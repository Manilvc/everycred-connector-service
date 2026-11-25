"""OpenTelemetry setup shared by every EveryCRED Python service.

This package is copied verbatim into each service (for example
``core/telemetry/`` or ``app/core/telemetry/``); the source of truth is
the ``everycred-telemetry`` folder. Keep ``TELEMETRY_VERSION`` in step
with that folder so a reviewer can tell whether a copy is current.
Every module starts with ``# fmt: off`` and ``# isort: skip_file`` so
each service's formatter (black at 88 columns, ruff at 79) leaves the
copy byte-identical to the source.

Typical use in a FastAPI service: call ``instrument_app(app)`` right
after creating the app, ``configure_telemetry("<service-name>")`` at
lifespan startup, and ``shutdown_telemetry(providers)`` at lifespan
shutdown. Celery workers call ``configure_telemetry(..., celery=True)``
from the ``worker_process_init`` signal. Engines created after
startup must come from ``telemetry.engines.create_traced_async_engine``
to be traced (that module needs SQLAlchemy, so it is not imported
here).

Telemetry stays off unless ``OTEL_EXPORTER_OTLP_ENDPOINT`` (or the
traces-specific variant) is set and ``OTEL_SDK_DISABLED`` is not true,
so a service without collector settings behaves exactly as before.
"""

# fmt: off
# isort: skip_file

from .bootstrap import (
    TelemetryProviders,
    configure_telemetry,
    instrument_app,
    is_telemetry_enabled,
    shutdown_telemetry,
)
from .logs import SPAN_ID_FIELD, TRACE_ID_FIELD, install_log_correlation
from .propagation import (
    current_span_id,
    current_trace_id,
    current_traceparent,
    link_from_traceparent,
)
from .redaction import RedactingSpanExporter, redact_attributes
from .spans import get_meter, get_tracer, span, traced

TELEMETRY_VERSION = "0.1.2"

__all__ = [
    "SPAN_ID_FIELD",
    "TELEMETRY_VERSION",
    "TRACE_ID_FIELD",
    "RedactingSpanExporter",
    "TelemetryProviders",
    "configure_telemetry",
    "current_span_id",
    "current_trace_id",
    "current_traceparent",
    "get_meter",
    "get_tracer",
    "install_log_correlation",
    "instrument_app",
    "is_telemetry_enabled",
    "link_from_traceparent",
    "redact_attributes",
    "shutdown_telemetry",
    "span",
    "traced",
]

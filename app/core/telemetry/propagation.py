"""Helpers for carrying trace context through storage and other tools.

Work that is queued in a database row and picked up later by a worker
cannot continue the original trace as a child span. Saving
``current_traceparent()`` with the row and turning it back into a span
link with ``link_from_traceparent()`` lets Tempo jump between the two
traces.
"""

# fmt: off
# isort: skip_file

from opentelemetry import trace
from opentelemetry.trace import Link
from opentelemetry.trace.propagation.tracecontext import (
    TraceContextTextMapPropagator,
)

TRACEPARENT_HEADER = "traceparent"
# A W3C traceparent is exactly 55 characters; anything longer stored in
# a row was not written by this package and is ignored.
TRACEPARENT_LENGTH = 55

_propagator = TraceContextTextMapPropagator()


def current_trace_id() -> str | None:
    """Return the active trace id as 32 hex characters, or None."""
    context = trace.get_current_span().get_span_context()
    if not context.is_valid:
        return None
    return trace.format_trace_id(context.trace_id)


def current_span_id() -> str | None:
    """Return the active span id as 16 hex characters, or None."""
    context = trace.get_current_span().get_span_context()
    if not context.is_valid:
        return None
    return trace.format_span_id(context.span_id)


def current_traceparent() -> str | None:
    """Return the active span as a W3C ``traceparent`` value, or None."""
    carrier: dict[str, str] = {}
    _propagator.inject(carrier)
    return carrier.get(TRACEPARENT_HEADER)


def link_from_traceparent(traceparent: str | None) -> Link | None:
    """Turn a stored ``traceparent`` into a span link.

    Args:
        traceparent: Value saved earlier with ``current_traceparent()``.

    Returns:
        A link to the stored span, or None when the value is empty or
        not a valid ``traceparent``.
    """
    if not traceparent or len(traceparent) != TRACEPARENT_LENGTH:
        return None
    context = _propagator.extract({TRACEPARENT_HEADER: traceparent})
    span_context = trace.get_current_span(context).get_span_context()
    if not span_context.is_valid:
        return None
    return Link(span_context)

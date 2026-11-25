"""Small helpers for business spans and metrics.

Spans created here record the exception *and* set an error status.
Tempo filters errors by status while the stack trace lives on the
exception event; doing only one leaves errors either unsearchable or
without detail.
"""

# fmt: off
# isort: skip_file

import functools
import inspect
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from typing import Any, TypeVar

from opentelemetry import metrics, trace
from opentelemetry.trace import Span, SpanKind, Status, StatusCode

from .redaction import redact_attributes

INSTRUMENTATION_NAME = "everycred"

FuncT = TypeVar("FuncT", bound=Callable[..., Any])


def get_tracer(name: str = INSTRUMENTATION_NAME) -> trace.Tracer:
    """Return a tracer; a no-op tracer while telemetry is off."""
    return trace.get_tracer(name)


def get_meter(name: str = INSTRUMENTATION_NAME) -> metrics.Meter:
    """Return a meter; a no-op meter while telemetry is off."""
    return metrics.get_meter(name)


@contextmanager
def span(
    name: str,
    *,
    kind: SpanKind = SpanKind.INTERNAL,
    attributes: Mapping[str, Any] | None = None,
    links: list[trace.Link] | None = None,
) -> Iterator[Span]:
    """Run a block inside a span that marks failures as errors.

    Args:
        name: Low-cardinality span name, e.g. ``"credential.revoke"``.
        kind: Span kind; ``INTERNAL`` for in-process work.
        attributes: Ids and outcomes only, never personal data. They
            are redacted again before export.
        links: Links to related traces, e.g. from a stored traceparent.

    Yields:
        The started span, for adding attributes as the work progresses.
    """
    tracer = get_tracer()
    with tracer.start_as_current_span(
        name,
        kind=kind,
        attributes=redact_attributes(attributes),
        links=links,
        record_exception=False,
        set_status_on_exception=False,
    ) as current:
        try:
            yield current
        except Exception as exc:
            current.record_exception(exc)
            current.set_status(Status(StatusCode.ERROR, type(exc).__name__))
            raise


def traced(
    name: str | None = None,
    *,
    attributes: Mapping[str, Any] | None = None,
) -> Callable[[FuncT], FuncT]:
    """Wrap a sync or async function in ``span()``.

    Args:
        name: Span name; defaults to ``module.qualname`` of the function.
        attributes: Fixed attributes added to every call's span.

    Returns:
        A decorator that keeps the function's signature and type.
    """

    def decorator(func: FuncT) -> FuncT:
        span_name = name or f"{func.__module__}.{func.__qualname__}"

        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                with span(span_name, attributes=attributes):
                    return await func(*args, **kwargs)

            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            with span(span_name, attributes=attributes):
                return func(*args, **kwargs)

        return sync_wrapper  # type: ignore[return-value]

    return decorator

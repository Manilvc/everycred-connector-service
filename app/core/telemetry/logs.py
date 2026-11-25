"""Add the active trace and span ids to every log record.

The ids are attached through a log record factory instead of a handler
filter, so handlers configured after telemetry starts (for example by a
later ``dictConfig`` call) still see them. Formatters reference the
fields by name: ``%(trace_id)s`` in text formats, or the attribute in
JSON formatters. Records outside a span get ``"-"`` so text formats
never fail on a missing field.
"""

# fmt: off
# isort: skip_file

import logging
from collections.abc import Callable

from opentelemetry import trace

TRACE_ID_FIELD = "trace_id"
SPAN_ID_FIELD = "span_id"
NO_TRACE = "-"

_installed = False


def _span_ids() -> tuple[str, str]:
    context = trace.get_current_span().get_span_context()
    if not context.is_valid:
        return NO_TRACE, NO_TRACE
    return (
        trace.format_trace_id(context.trace_id),
        trace.format_span_id(context.span_id),
    )


def _wrap_factory(
    previous: Callable[..., logging.LogRecord],
) -> Callable[..., logging.LogRecord]:
    def factory(*args: object, **kwargs: object) -> logging.LogRecord:
        record = previous(*args, **kwargs)
        trace_id, span_id = _span_ids()
        setattr(record, TRACE_ID_FIELD, trace_id)
        setattr(record, SPAN_ID_FIELD, span_id)
        return record

    return factory


def install_log_correlation() -> None:
    """Make every new log record carry ``trace_id`` and ``span_id``.

    Safe to call more than once; only the first call wraps the factory.
    It is also safe while telemetry is disabled, in which case every
    record gets ``"-"``.
    """
    global _installed
    if _installed:
        return
    logging.setLogRecordFactory(_wrap_factory(logging.getLogRecordFactory()))
    _installed = True

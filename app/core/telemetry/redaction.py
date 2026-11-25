"""Remove personal data and secrets from spans before they leave the process.

Instrumentation libraries decide which attributes a span carries, and
some of them record URLs with query strings or, when configured, request
headers. This exporter wrapper is the in-process half of the redaction
rule; the collector applies the same rule again so a service with an
outdated copy of this package still cannot leak.

Span attributes are immutable once a span ends, so redaction rebuilds
each span as a new ``ReadableSpan`` with cleaned attributes instead of
editing it in place.
"""

# fmt: off
# isort: skip_file

import re
from collections.abc import Mapping, Sequence
from typing import Any

from opentelemetry.sdk.trace import Event, ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

REDACTED = "[redacted]"

# Attribute keys whose value is dropped whatever it contains. Matching
# is by substring on the lower-cased key, so ``http.request.header.
# authorization`` and ``user.email`` are both caught.
_DENIED_KEY_PARTS = (
    "authorization",
    "cookie",
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "api-key",
    "apikey",
    "x-holder-email",
    "email",
    "phone",
    "mobile",
    "enduser.",
    "subject_id",
    "employee_number",
)

# Keys holding a full URL or path whose query string is removed. Query
# strings carry emails and one-time codes on several EveryCRED routes.
_URL_KEYS = ("http.url", "http.target", "url.full", "http.route.raw")
_DROPPED_KEYS = ("url.query",)

_EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_BEARER_PATTERN = re.compile(r"(?i)bearer\s+[\w.~+/=-]+")


def _is_denied_key(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in _DENIED_KEY_PARTS)


def _strip_query(url: str) -> str:
    return url.split("?", 1)[0]


def _clean_text(text: str) -> str:
    text = _EMAIL_PATTERN.sub(REDACTED, text)
    return _BEARER_PATTERN.sub(REDACTED, text)


def _clean_value(value: Any) -> Any:
    if isinstance(value, str):
        return _clean_text(value)
    if isinstance(value, Sequence) and not isinstance(value, bytes):
        return tuple(
            _clean_text(item) if isinstance(item, str) else item
            for item in value
        )
    return value


def redact_attributes(
    attributes: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Return a copy of span attributes with sensitive data removed.

    Denied keys are replaced with ``[redacted]`` rather than dropped so
    a reader can see that a value existed. Query strings are cut from
    URL attributes, and emails and bearer tokens are masked inside any
    remaining string value.

    Args:
        attributes: Attributes as recorded on a span or event.

    Returns:
        A new mapping that is safe to export.
    """
    if not attributes:
        return {}
    cleaned: dict[str, Any] = {}
    for key, value in attributes.items():
        if key in _DROPPED_KEYS:
            continue
        if _is_denied_key(key):
            cleaned[key] = REDACTED
        elif key in _URL_KEYS and isinstance(value, str):
            cleaned[key] = _clean_text(_strip_query(value))
        else:
            cleaned[key] = _clean_value(value)
    return cleaned


def _redact_event(event: Event) -> Event:
    return Event(
        name=event.name,
        attributes=redact_attributes(event.attributes),
        timestamp=event.timestamp,
    )


def _redact_span(span: ReadableSpan) -> ReadableSpan:
    return ReadableSpan(
        name=_clean_text(span.name),
        context=span.context,
        parent=span.parent,
        resource=span.resource,
        attributes=redact_attributes(span.attributes),
        events=tuple(_redact_event(event) for event in span.events),
        links=span.links,
        kind=span.kind,
        status=span.status,
        start_time=span.start_time,
        end_time=span.end_time,
        instrumentation_scope=span.instrumentation_scope,
    )


class RedactingSpanExporter(SpanExporter):
    """Wrap a span exporter so every span is redacted before export.

    Attributes:
        inner: The exporter that receives the cleaned spans.
    """

    def __init__(self, inner: SpanExporter) -> None:
        self.inner = inner

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        """Redact the batch and hand it to the wrapped exporter."""
        return self.inner.export([_redact_span(span) for span in spans])

    def shutdown(self) -> None:
        """Shut down the wrapped exporter."""
        self.inner.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        """Flush the wrapped exporter."""
        return self.inner.force_flush(timeout_millis)

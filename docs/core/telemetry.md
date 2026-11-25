# `app/core/telemetry/`

> Last updated: 2026-11-24

## Purpose

Send traces and metrics to the EveryCRED OpenTelemetry collector and
put the trace id on every log line, so a wallet action can be followed
from the holder service through the connector to each DCS in Grafana
(Tempo for traces, Prometheus for metrics, Loki for logs).

The package is a **verbatim copy** of `everycred-telemetry/telemetry/`
(version in `TELEMETRY_VERSION`). Do not edit it here: change the
shared folder, bump the version, and copy it into every service.

Telemetry is off unless `OTEL_EXPORTER_OTLP_ENDPOINT` is set, so a
local run without a collector behaves exactly as before.

## Where telemetry starts

| Step | Where | What it does |
|---|---|---|
| `instrument_app(app)` | `create_app()` in `app/main.py`, right after `FastAPI(...)` | Adds the server-span middleware. It must run before the first request builds the middleware stack. |
| `configure_telemetry("everycred-connector-service", ...)` | `lifespan()` in `app/main.py` | Creates the tracer and meter providers and the OTLP/HTTP exporters, and instruments SQLAlchemy (the lifespan engine) and httpx. It runs inside the worker process because the exporters start threads that would not survive a fork. |
| `configure_telemetry("everycred-connector-worker", ...)` | `run_forever()` in `app/worker.py`, after the database engine is created | The worker is a separate process, so it starts its own exporters. Its engine is passed in `engines=`. |
| `shutdown_telemetry(telemetry)` | `lifespan()` shutdown and the `finally` in `run_forever()` | Flushes queued spans and metrics. The worker runs it on SIGTERM too, because a set stop event leaves the loop through the same `finally`. |
| `install_log_correlation()` | `configure_logging()` in `app/core/logging.py` | Adds `trace_id` and `span_id` to every log record (see [logging](logging.md)). |

The worker's outbound HTTP calls to the holder service are traced, and
its database queries are too.

## Worker spans

Each round of `app/worker.py` runs one job, and the job has its own root
span:

| Span | Attributes |
|---|---|
| `holder_notification.deliver_due` | `everycred.worker.batch_size`, `everycred.worker.processed` |

`processed` is the number of outbox rows delivered to the holder
service. A job that raises records the exception and sets the span to
error, and the round logs `Worker round failed` as before. The request
that sends a holder's event through the holder service is not linked to
this span: the outbox row stores no `traceparent`. Saving
`current_traceparent()` on `HolderNotification` and passing it to
`link_from_traceparent()` would link them, but that needs a migration
and is not part of this change.

Rounds run every `WORKER_INTERVAL_SECONDS` (5 seconds by default), so a
round with nothing due still produces a span with `processed` set to 0.
Filter those in the collector if they are too many for Tempo.

## What is traced

- **Every HTTP request** gets a SERVER span named after the route
  template, for example `POST /v1/holders/operations`. Health, metrics
  and docs routes are excluded. A `traceparent` sent by the holder
  service makes the span a child of the holder's trace.
- **Database queries** get CLIENT spans, children of the request span,
  with the statement and placeholders only, never parameters.
- **Every outbound call to a DCS** (`SourceCaller`) gets a CLIENT span,
  and the request carries a W3C `traceparent` header so the DCS can
  continue the trace. `X-Request-ID` is still sent.
- **`connector.operation`** wraps `OperationService.run` in
  `app/features/operations/service.py`:

  | Attribute | Value |
  |---|---|
  | `everycred.operation` | Catalog name, e.g. `requests.get`; `unknown` for a name outside the catalog |
  | `everycred.result` | `ok`, `partial`, `failed`, `rejected` or `error` |
  | `everycred.source_count` | Sources called (only when the call ran) |

  `rejected` means an `AppError` before any source was called (unknown
  operation, bad params, unlinked holder); `partial` and `failed` mean
  some or all sources did not answer with 2xx.

## Metrics

| Metric | Type | Attributes |
|---|---|---|
| `everycred.holder.operations` | Counter | `operation`, `result` (same values as the span) |

The FastAPI and httpx instrumentation also record their standard HTTP
duration histograms.

## Configuration

Standard OpenTelemetry environment variables only:

| Variable | Example | Notes |
|---|---|---|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4318` | Empty (default) turns telemetry off. Port 4318 is OTLP over HTTP. |
| `OTEL_SDK_DISABLED` | `false` | `true` turns everything off even with an endpoint. |
| `OTEL_RESOURCE_ATTRIBUTES` | `deployment.environment=local` | `service.name` and `service.namespace` are set in code. |
| `OTEL_TRACES_SAMPLER` | `parentbased_traceidratio` | Follows the holder service's sampling decision. |
| `OTEL_TRACES_SAMPLER_ARG` | `1.0` | Ratio for new traces; `0.1` in production. |

`service.version` comes from `SERVICE_VERSION`.

Never set `OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_*`: requests carry
`X-API-Key`, `X-Admin-Key` and `X-Holder-Email`.

## Adding a span or a metric

```python
from app.core.telemetry import get_meter, span

lookups_counter = get_meter().create_counter(
    "everycred.credential_lookups",
    description="Credential lookups by result.",
)


async def lookup(source_code: str) -> None:
    with span("credential.lookup", attributes={"source.code": source_code}):
        ...
    lookups_counter.add(1, {"result": "ok"})
```

- Span names are `<domain>.<action>` and low-cardinality: never put an
  id in the name.
- `span()` records an exception and marks the span as an error, then
  re-raises.
- Metric names start with `everycred.`. Metric attributes have a small,
  fixed set of values; never ids, tenant ids or client input (see how
  `UNKNOWN_OPERATION` caps operation names).

## New database engines

The lifespan engine is passed to `configure_telemetry(engines=...)`.
An engine created later must come from
`create_traced_async_engine()` in `app/core/telemetry/engines.py`;
`app/core/database.py` imports `create_async_engine` directly, so an
engine it creates after startup would record no query spans.

## Forbidden attributes

Never put these on a span or a metric: holder emails or the
`X-Holder-Email` header, names, phone numbers, API keys, webhook
secrets, subject or employee ids, request or response bodies,
credential content. Use the source code, the client id or the holder
key hash instead.

The FastAPI and httpx instrumentation do not record headers or bodies
unless `OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_*` is set, so the
holder email (sent in the JSON body by the holder service and in the
`X-Holder-Email` header to a DCS) never reaches a span. Source URLs are
built from catalog templates and `Identifier` params only.
`RedactingSpanExporter` and the collector also redact email-shaped
values and keys containing `email`, `token` or `api_key`, as a safety
net.

## Failure modes

| Situation | Behaviour |
|---|---|
| No endpoint set | Everything is a no-op; logs show `trace_id=-`. |
| Collector unreachable | The batch exporter drops spans after its retries and logs a warning; requests are unaffected. |
| SQLAlchemy upgrade | The SQLAlchemy instrumentation declares support for < 2.1 only; the shared package skips that check because it works on 2.1. If an upgrade breaks it, database spans are the first thing to check. |

## Tests

`tests/core/test_worker_telemetry.py` covers the worker: the delivery job
gets its span with the batch size and delivered count, a failing job
marks its span as an error and re-raises, a log line inside the job
carries its ids, `run_forever()` starts telemetry as
`everycred-connector-worker` and stops it, and no exporter is created
without an endpoint.

`tests/core/test_telemetry.py`, using the session-scoped in-memory
providers from `tests/conftest.py` (`telemetry` fixture). OpenTelemetry
allows global providers to be set once per process, so tests share
them; spans are cleared and counters use delta temporality so each
test reads only its own data. They cover: tracing is attached only with
an endpoint, a request produces a SERVER span with query children, the
`connector.operation` span and `everycred.holder.operations` counter
for `ok`, `rejected` and `failed`, the `traceparent` on the outbound
DCS call, no span holds the holder email or `X-Holder-Email`, and the
request log line carries the trace id.

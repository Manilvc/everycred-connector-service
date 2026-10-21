# `app/core/logging.py`

> Last updated: 2026-10-21

## Purpose

Configures the root logger once per process. Every line includes the
current request id, and deployed environments get one JSON object per
line.

Called from two places:

- `create_app()` in `app/main.py`, for the API process.
- `main()` in `app/worker.py`, for the worker process.

## Public API

### `configure_logging(level: str, use_json: bool) -> None`

Replaces the root logger's handlers with one `StreamHandler` on stdout.

- `level` is the minimum level name, e.g. `"INFO"`.
- `use_json=True` uses `JsonFormatter`. `False` uses `TEXT_LOG_FORMAT`.

Also routes Uvicorn's `uvicorn` and `uvicorn.error` loggers through the
root handler, and disables `uvicorn.access`. The access log is replaced
by the one line per request that `RequestContextMiddleware` writes.

```python
from app.core.logging import configure_logging

configure_logging("INFO", use_json=True)
```

### `class RequestIdFilter(logging.Filter)`

Sets `record.request_id` to `get_request_id()`, or `"-"` outside a
request. It always returns `True`, so no record is dropped.

### `class JsonFormatter(logging.Formatter)`

Writes one JSON object per record with these keys:

| Key | Value |
|---|---|
| `timestamp` | ISO 8601 UTC time |
| `level` | Level name |
| `logger` | Logger name, e.g. `app.features.sources.service` |
| `message` | Formatted message |
| `request_id` | Request id, or `null` |
| `exception` | Traceback text, only when there is one |

Example line:

```json
{"timestamp": "2026-10-21T10:00:00.000000+00:00", "level": "INFO", "logger": "app.features.sources.service", "message": "Registered source dcs-india", "request_id": "3f9c2a1e0b7d4f58a6c1d2e3f4a5b6c7"}
```

### `TEXT_LOG_FORMAT`

`"%(asctime)s %(levelname)-8s [%(request_id)s] %(name)s: %(message)s"`.
Used when `LOG_JSON=false`.

## How it works

1. `configure_logging` builds a `StreamHandler` on `sys.stdout` and adds
   `RequestIdFilter` to it. The filter sets `request_id` on each record
   as it is emitted.
2. The formatter is `JsonFormatter` or the text format.
3. The root logger's handlers are cleared and replaced, so a second call
   does not duplicate lines.
4. Uvicorn loggers are set to propagate to the root logger.

Modules create their own loggers with `logging.getLogger(__name__)`.

## Configuration

| Setting / env var | Default | Effect |
|---|---|---|
| `LOG_LEVEL` | `INFO` | Root level |
| `LOG_JSON` | `true` | JSON lines when true, text otherwise |

## Failure modes

| Situation | Behaviour | Logged as |
|---|---|---|
| Log record emitted outside a request | `request_id` is `"-"` (text) or `null` (JSON) | Normal level |
| Exception info present | Traceback text added to the `exception` key | Record's own level |

## Changing this module

- Log with lazy arguments: `logger.info("Registered source %s", code)`.
  Do not use f-strings in log calls.
- Never log secrets, tokens, or full request bodies. The codebase logs
  source codes, client ids, and delivery ids.
- Changing the JSON keys affects whatever indexes these logs. Add keys
  rather than renaming them.
- `configure_logging` clears the root handlers. Call it once per process,
  at start-up.

## Tests

No dedicated module. The request id filter is exercised indirectly by
any test that makes a request. Setting `LOG_JSON=false` in
`tests/conftest.py` keeps test output in the text format.

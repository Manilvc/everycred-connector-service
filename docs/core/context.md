# `app/core/context.py`

> Last updated: 2026-10-21

## Purpose

Holds the per-request id in a `contextvars.ContextVar`, so code deep in
the call stack can read it without passing it through function arguments.
Three consumers read it:

- `build_error_body` in `app/core/exceptions.py`, for `request_id` in
  error responses.
- `RequestIdFilter` in `app/core/logging.py`, for log lines.
- `_forward_request_id` in `app/core/http_client.py`, which passes the id
  to outbound calls.

## Public API

### `REQUEST_ID_HEADER: str`

`"X-Request-ID"`. The header read on the way in and written on the way
out.

### `request_id_context: ContextVar[str | None]`

Default `None`. `RequestContextMiddleware` sets it for each request and
resets it after the response.

### `get_request_id() -> str | None`

Returns the current request's id, or `None` outside a request. The
worker never sets it, so worker log lines show `-`.

```python
from app.core.context import get_request_id

request_id = get_request_id()  # None outside a request
```

## How it works

1. `RequestContextMiddleware` calls `request_id_context.set(request_id)`
   and keeps the token.
2. Anything the request runs reads the value with `get_request_id()`.
3. The middleware calls `request_id_context.reset(token)` in `finally`,
   which restores the previous value.

`asyncio.gather` and `asyncio.create_task` copy the current context into
each task, so tasks started inside a request see its id.

## Configuration

None.

## Failure modes

| Situation | Behaviour | Logged as |
|---|---|---|
| Read outside a request | Returns `None` | Not logged |
| Read in a background task started outside a request | Returns `None` | Not logged |

## Changing this module

- Store only the request id here. Other per-request state belongs in its
  own context variable with its own reset.
- The name `REQUEST_ID_HEADER` is also used by the middleware and the
  HTTP client. Change it in one place only.

## Tests

No dedicated module. Covered through the middleware and the error
envelope tests in `tests/features/`.

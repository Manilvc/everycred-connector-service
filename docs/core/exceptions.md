# `app/core/exceptions.py`

> Last updated: 2026-10-21

## Purpose

Defines the error types services raise and the handlers that turn them
into the shared error envelope. Services raise `AppError` subclasses and
never build HTTP responses. Routers do not catch domain errors.

Every API error has this shape:

```json
{
  "error": {
    "code": "source_not_found",
    "message": "Source dcs-india does not exist.",
    "request_id": "3f9c2a1e0b7d4f58a6c1d2e3f4a5b6c7"
  }
}
```

`details` appears only for validation errors. `request_id` matches the
`X-Request-ID` response header.

## Public API

### `class AppError(Exception)`

Base class for errors that are safe to show to clients.

| Attribute | Default | Meaning |
|---|---|---|
| `status_code` | `400` | HTTP status |
| `error_code` | `"bad_request"` | Stable machine-readable code |
| `headers` | `None` | Extra response headers |
| `message` | (constructor argument) | Shown to the client as-is |

The message must not contain secrets, personal data, or internal detail.
Log those separately.

### Subclasses

| Class | Status | `error_code` | Used for |
|---|---|---|---|
| `AuthenticationError` | 401 | `authentication_failed` | Missing or wrong `X-Admin-Key` or `X-API-Key`. Adds `WWW-Authenticate: Bearer` |
| `PermissionDeniedError` | 403 | `permission_denied` | Verifier calling a holder-only route |
| `NotFoundError` | 404 | `not_found` | Base for feature not-found errors |
| `ConflictError` | 409 | `conflict` | Base for feature conflict errors |
| `ExternalServiceError` | 502 | `external_service_error` | Base for failures in a DCS source |

Feature modules subclass these and set their own `error_code`, for
example `SourceNotFoundError` (`source_not_found`) in
`app/features/sources/exceptions.py`.

```python
from app.core.exceptions import NotFoundError


class ClientNotFoundError(NotFoundError):
    """Raised when no client has the requested id."""

    error_code = "client_not_found"
```

### `build_error_body(error_code, message, details=None) -> dict[str, Any]`

Builds the envelope for the current request, including the request id
from `get_request_id()`. Fields that are `None` are left out.

### `register_exception_handlers(app: FastAPI) -> None`

Registers three handlers:

| Raised | Handler | Response |
|---|---|---|
| `AppError` | `handle_app_error` | The error's status, code, and message. Its `headers` are added |
| `RequestValidationError` | `handle_validation_error` | 422 `validation_error`, message "The request is invalid.", `details` |
| `StarletteHTTPException` | `handle_http_error` | The same status. `error_code` is the HTTP phrase in lower case with underscores, e.g. `not_found`, `method_not_allowed` |

For validation errors, `details` lists `loc`, `msg`, and `type` for each
problem. The rejected input is never echoed, because it may contain
personal data.

Unhandled exceptions are not handled here. `RequestContextMiddleware`
catches them, so the log line has the request id.

## How it works

1. A service raises an `AppError` subclass.
2. FastAPI calls `handle_app_error`. It logs one line at `INFO` with the
   code and message, then returns the envelope.
3. Request validation fails before the route runs. FastAPI raises
   `RequestValidationError`, and `handle_validation_error` returns 422.
4. Anything else reaches `RequestContextMiddleware`, which logs it and
   returns 500 `internal_error`.

## Configuration

None.

## Failure modes

| Situation | Behaviour | Logged as |
|---|---|---|
| `AppError` raised | Status and envelope from the class | `INFO` |
| Validation fails | 422 `validation_error` with `details` | Not logged |
| Route or method not found | 404 or 405 with the HTTP phrase as code | Not logged |
| Non-`AppError` exception | 500 `internal_error`, generic message | `ERROR` with traceback (middleware) |

Because `AppError` is logged at `INFO`, a burst of 4xx responses does not
create `ERROR` noise. Anything at `ERROR` is a real fault.

## Changing this module

- A new error type is a subclass of the closest base class with a new
  `error_code`. Pick the code once and keep it stable. Clients branch on it.
- Do not put a DCS response body, a key, or an email in `message`.
- Do not catch `AppError` in routers. Let it propagate.
- `AuthenticationError` sets a `WWW-Authenticate` header. The webhook
  error `InvalidSignatureError` clears it, because webhook senders do not
  use bearer tokens (see `app/features/events/exceptions.py`).
- The handler set is registered in `app/main.py` through
  `register_exception_handlers`.

## Tests

No dedicated module. Status codes and envelopes are asserted in the
feature tests, for example `tests/features/sources/test_sources.py`
(`test_create_source_requires_admin_key`) and
`tests/features/events/test_events.py` (`test_wrong_signature_is_rejected`).

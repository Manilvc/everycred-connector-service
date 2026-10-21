# `app/core/http_client.py`

> Last updated: 2026-10-21

## Purpose

Builds the one `httpx.AsyncClient` used for outbound calls: to DCS
sources and to the holder service. Timeouts, pool limits, and redirect
policy are set in one place. Connection pools are shared across requests.

## Public API

### `create_http_client(settings: Settings) -> httpx.AsyncClient`

Returns a configured client. The caller owns it and must call `aclose()`.

| Option | Value | Reason |
|---|---|---|
| `timeout` | `httpx.Timeout(settings.http_timeout_seconds)` | Default when a call does not pass its own |
| `limits` | `max_connections=settings.http_max_connections` | Caps sockets per process |
| `headers` | `User-Agent: {service_name}/{service_version}` | Identifies the connector to partners |
| `follow_redirects` | `False` | A redirect could send `X-API-Key` to another host |
| `event_hooks` | `{"request": [_forward_request_id]}` | Sends the request id upstream |

### `get_http_client(request: Request) -> httpx.AsyncClient`

Returns `request.state.http_client`, set in the lifespan of `app/main.py`.

### `HttpClient`

`Annotated[httpx.AsyncClient, Depends(get_http_client)]`. Used by the
event and notification dependencies.

```python
from app.core.http_client import HttpClient


async def handler(http_client: HttpClient) -> None:
    response = await http_client.get("https://dcs-india.example.com/v1/ping")
```

Calls made through the shared client pass their own timeout. Source
calls use `SOURCE_TIMEOUT_SECONDS` and holder-service deliveries use
`NOTIFICATION_TIMEOUT_SECONDS`. See `SourceCaller.call` and
`NotificationService._post`.

## How it works

1. `create_http_client` is called once in the lifespan. The worker calls
   it once in `run_forever`.
2. For every outbound request, httpx runs `_forward_request_id`. It sets
   `X-Request-ID` to the current request's id, if there is one. The
   worker has no request id, so the header is not set there.
3. The client is closed in the lifespan's `finally` block, or in the
   worker's `finally` block.

Forwarding the id lets a partner match a failed call on their side to
the connector's log line.

## Configuration

| Setting / env var | Default | Effect |
|---|---|---|
| `HTTP_TIMEOUT_SECONDS` | `10.0` | Default timeout |
| `HTTP_MAX_CONNECTIONS` | `100` | Maximum open connections |
| `SERVICE_NAME`, `SERVICE_VERSION` | see `config.md` | `User-Agent` value |

## Failure modes

| Situation | Behaviour | Logged as |
|---|---|---|
| Timeout | `httpx.TimeoutException`, handled by the caller | Caller decides (see `sources/caller.py`) |
| Connection error | `httpx.HTTPError`, handled by the caller | Caller decides |
| Redirect returned by a partner | Response returned as is, not followed | Not logged here |

## Changing this module

- Do not create clients elsewhere. Use `HttpClient` in routes and the
  shared client in `NotificationService`.
- Keep `follow_redirects=False`. Following a redirect would send
  credentials to an address the operator did not register.
- Keep a timeout on every call. Pass one explicitly if it differs from the
  default.

## Tests

No dedicated module. Source calls are faked in `tests/conftest.py` with
`FakeSources`, which replaces the transport. Delivery is exercised in
`tests/features/notifications/test_delivery.py`.

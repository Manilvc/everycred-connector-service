# `app/core/signatures.py`

> Last updated: 2026-10-21

## Purpose

HMAC-SHA256 signing and verification for webhooks in both directions:

- **Inbound**: DCS sources sign the events they send to
  `POST /v1/sources/{source_code}/events`. `EventService` verifies them.
- **Outbound**: the connector signs the notifications it sends to the
  holder service. `NotificationService` signs them.

Both directions use the same scheme, so the holder service and every DCS
verify webhooks the same way.

## Public API

### Header names

| Constant | Value |
|---|---|
| `EVENT_HEADER` | `X-EveryCRED-Event` |
| `DELIVERY_HEADER` | `X-EveryCRED-Delivery` |
| `SIGNATURE_HEADER` | `X-EveryCRED-Signature` |

### `encode_body(payload: dict[str, Any]) -> bytes`

Serialises the payload as compact JSON with sorted keys. The sender signs
and sends these exact bytes. The receiver must verify the raw body, not a
re-serialised copy.

### `sign(secret: str, timestamp: int, body: bytes) -> str`

Returns the header value `t=<timestamp>,v1=<hex digest>`. The digest is
HMAC-SHA256 over `"<timestamp>."` followed by `body`, keyed with `secret`.

```python
import time

from app.core.signatures import encode_body, sign

body = encode_body({"id": "abc", "event": "credential.issued"})
header = sign("whsec_example", int(time.time()), body)
```

### `is_signature_valid(secret, header, body, tolerance_seconds, now=None) -> bool`

Returns `True` only if all of these hold:

1. The header parses as `t=<int>,v1=<value>`. Otherwise `False`.
2. `abs(now - t) <= tolerance_seconds`. `now` defaults to `time.time()`.
3. The recomputed digest equals `v1`, compared with
   `hmac.compare_digest`.

Never raises for a malformed header. It returns `False`.

## How it works

1. **Sender** — `NotificationService._post` calls `encode_body`, then
   `sign` with the current time. It sends the body and the three headers.
2. **Receiver** — `EventService._verify_signature` reads the raw request
   body (`_read_limited_body` in `app/features/events/router.py`), then
   calls `is_signature_valid` with the source's decrypted secret and
   `WEBHOOK_TOLERANCE_SECONDS`.
3. The timestamp check comes before the digest check, so a stale request
   is rejected without computing an HMAC.
4. The digest comparison is constant time.

Sign the same bytes that go on the wire. Anything that changes the body
after signing breaks verification.

## Configuration

| Setting / env var | Default | Effect |
|---|---|---|
| `WEBHOOK_TOLERANCE_SECONDS` | `300` | Maximum clock difference for inbound webhooks |
| `HOLDER_SERVICE_WEBHOOK_SECRET` | `None` | Secret for outbound signing. Required with the URL |
| Per-source webhook secret | Generated, stored encrypted | Secret for inbound verification (`whsec_...`) |

## Failure modes

| Situation | Result |
|---|---|
| Header missing | `is_signature_valid` returns `False`. The event route returns 401 `invalid_signature` |
| Timestamp outside tolerance | `False`. 401 `invalid_signature` |
| Digest mismatch | `False`. 401 `invalid_signature` |
| Header not parseable | `False`. 401 `invalid_signature` |

The receiver logs `Rejected unsigned webhook from <source code>` at
`WARNING`. It does not log the header or the body.

## Changing this module

- Changing the scheme breaks every DCS and the holder service at once.
  Add a `v2` value beside `v1` rather than replacing it.
- `X-EveryCRED-Event` is part of the header set but is not part of the
  signed data. The receiver takes the event type from the body. The
  signature covers the body only.
- Keep `hmac.compare_digest`. Do not compare digests with `==`.

## Tests

`tests/core/test_signatures.py` covers canonical encoding, tampering,
expiry, and malformed headers. Verification is also covered through
the event route in
`tests/features/events/test_events.py` (`test_wrong_signature_is_rejected`,
`test_stale_signature_is_rejected`). The outbound signature is checked in
`tests/features/notifications/test_delivery.py`
(`test_worker_delivers_a_signed_event_and_clears_the_payload`).

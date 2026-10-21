# `app/core/encryption.py`

> Last updated: 2026-10-21

## Purpose

Encrypts values the service has to read back in plain text. These are
the DCS source API keys, the webhook secrets the connector issues to
sources, and the outbox payloads that hold holder emails until delivery.

Values that only need to be compared, such as client API keys, are
hashed instead. See [security.md](security.md).

Encryption uses `cryptography.fernet.MultiFernet`. Each key is a Fernet
key (AES-128-CBC with HMAC-SHA256). The first configured key encrypts,
and every configured key is tried when decrypting. That allows key
rotation without downtime.

## Public API

### `encrypt_text(plaintext: str, settings: Settings) -> str`

Returns the ciphertext as a URL-safe string, encrypted with the first key.

### `decrypt_text(ciphertext: str, settings: Settings) -> str`

Returns the plaintext.

Raises:

- `DecryptionError` if the token is invalid or no configured key matches.

### `class DecryptionError(Exception)`

Raised by `decrypt_text`. The message is generic ("Stored value could
not be decrypted.") and does not include the ciphertext.

```python
from app.core.encryption import decrypt_text, encrypt_text

stored = encrypt_text("api-key-of-the-source", settings)
assert decrypt_text(stored, settings) == "api-key-of-the-source"
```

## How it works

1. `_cipher(settings)` reads `DATA_ENCRYPTION_KEYS` and passes the raw
   string to `_build_cipher`.
2. `_build_cipher` is cached with `lru_cache(maxsize=4)`. It splits the
   string on commas, builds one `Fernet` per key, and wraps them in a
   `MultiFernet`. The cache key is the raw string, so a change to the
   setting produces a new cipher. The cache is not cleared on rotation,
   and the old entries age out.
3. `encrypt_text` encrypts with the first key only.
4. `decrypt_text` catches `InvalidToken` from `MultiFernet` and raises
   `DecryptionError` from it.

Keys are validated at startup by `Settings.check_encryption_keys`, so
`_build_cipher` never receives a malformed key in a running process.

## Configuration

| Setting / env var | Default | Effect |
|---|---|---|
| `DATA_ENCRYPTION_KEYS` | (required) | Comma-separated Fernet keys. The first encrypts. All decrypt |

Generate a key with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Failure modes

| Situation | Behaviour | Logged as |
|---|---|---|
| Ciphertext from an unknown key | `DecryptionError` | Not logged here |
| Tampered ciphertext | `DecryptionError` | Not logged here |
| Caller does not catch `DecryptionError` | Propagates to the middleware, 500 `internal_error` | `ERROR` with traceback |

Callers do not catch `DecryptionError`. `SourceCaller.call` decrypts the
source API key, and `NotificationService._deliver` decrypts the outbox
payload. Neither handles the error. See Known limitations below.

## Changing this module

- Rotation: add the new key to the front of `DATA_ENCRYPTION_KEYS`, keep
  the old key behind it, and restart. Existing rows still decrypt. New
  writes use the new key. Remove the old key only after no row needs it.
- Nothing in the code re-encrypts existing rows. `MultiFernet.rotate` is
  not called. To move old rows to the new key, write a one-off script
  that reads and rewrites each encrypted column, then retire the old key.
- Do not log plaintext or ciphertext. Ciphertext is not secret, but it is
  noise, and it can be used to test a key guess offline.

## Known limitations

- A row that cannot be decrypted raises `DecryptionError` at the point
  of use. The outbox catches it per row and marks only that row
  `failed` (see [notifications.md](../features/notifications.md)).

## Tests

`tests/core/test_security_and_encryption.py` covers the round trip and
a value encrypted with a foreign key. Storage through the API is covered
by `tests/features/sources/test_sources.py`, and an unreadable outbox row
by `tests/features/notifications/test_delivery.py`.

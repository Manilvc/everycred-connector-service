"""Authentication of operators and client applications.

Two kinds of callers use the API:

* **Operators** manage sources and clients with the single
  ``ADMIN_API_KEY`` from settings, sent as ``X-Admin-Key``.
* **Clients** (verifier applications and the holder service) send a
  key issued by an operator as ``X-API-Key``.

A client key looks like ``ecc_3f9a1c07b2de_<43 random characters>``.
The 12-character hex prefix is stored in plain text for lookups; only an
HMAC-SHA256 of the full key is stored, keyed with a server-side secret,
so a leaked database alone cannot be used to confirm a key.
"""

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Security
from fastapi.security import APIKeyHeader

from app.core.config import Settings, SettingsDep
from app.core.exceptions import AuthenticationError

API_KEY_SCHEME = "ecc"
_PREFIX_BYTES = 6
_SECRET_BYTES = 32
PREFIX_LENGTH = _PREFIX_BYTES * 2

_admin_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=False)


@dataclass(frozen=True, slots=True)
class GeneratedApiKey:
    """A newly created client key, before it is stored.

    Attributes:
        plaintext: The full key. Return it to the caller once and never
            store or log it.
        prefix: Lookup identifier saved alongside the hash.
        key_hash: Hex HMAC-SHA256 of ``plaintext`` to store.
    """

    plaintext: str
    prefix: str
    key_hash: str


def hash_api_key(api_key: str, settings: Settings) -> str:
    """Return the hex HMAC-SHA256 of ``api_key``."""
    return hmac.new(
        settings.api_key_hash_secret.get_secret_value().encode(),
        api_key.encode(),
        hashlib.sha256,
    ).hexdigest()


def generate_api_key(settings: Settings) -> GeneratedApiKey:
    """Create a random client key and the values needed to store it."""
    prefix = secrets.token_hex(_PREFIX_BYTES)
    secret = secrets.token_urlsafe(_SECRET_BYTES)
    plaintext = f"{API_KEY_SCHEME}_{prefix}_{secret}"
    return GeneratedApiKey(
        plaintext=plaintext,
        prefix=prefix,
        key_hash=hash_api_key(plaintext, settings),
    )


def extract_api_key_prefix(api_key: str) -> str | None:
    """Return the lookup prefix of ``api_key``, or None if malformed."""
    # maxsplit=2 because the secret part may itself contain underscores.
    parts = api_key.split("_", 2)
    if len(parts) != 3:
        return None
    scheme, prefix, secret = parts
    if scheme != API_KEY_SCHEME or len(prefix) != PREFIX_LENGTH or not secret:
        return None
    return prefix


def is_api_key_valid(
    api_key: str, stored_hash: str, settings: Settings
) -> bool:
    """Compare ``api_key`` with a stored hash in constant time."""
    return hmac.compare_digest(hash_api_key(api_key, settings), stored_hash)


def require_admin(
    settings: SettingsDep,
    admin_key: Annotated[str | None, Security(_admin_key_header)],
) -> None:
    """Allow the request only with the operator key.

    Raises:
        AuthenticationError: The header is missing or wrong.
    """
    expected = settings.admin_api_key.get_secret_value()
    if admin_key is None or not hmac.compare_digest(
        admin_key.encode(), expected.encode()
    ):
        raise AuthenticationError("A valid X-Admin-Key header is required.")


AdminOnly = Depends(require_admin)

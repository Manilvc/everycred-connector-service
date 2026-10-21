"""Pseudonymous holder identifiers for the routing table."""

import hashlib
import hmac

from app.core.config import Settings


def normalise_email(email: str) -> str:
    """Return ``email`` trimmed and lower-cased for comparison."""
    return email.strip().lower()


def holder_key(email: str, settings: Settings) -> str:
    """Return the keyed hash that stands in for a holder's email.

    DCS sources and the holder service both identify a holder by email;
    hashing it with a server-side secret lets the connector match them
    without keeping the address.
    """
    return hmac.new(
        settings.holder_key_secret.get_secret_value().encode(),
        normalise_email(email).encode(),
        hashlib.sha256,
    ).hexdigest()

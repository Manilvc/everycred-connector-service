"""The standard credential shape and the normalizer registry.

Each DCS source answers in its own format. A normalizer turns one raw
answer into :class:`NormalizedCredential`, so verifier applications and
the holder service read one shape whatever the source. A source names
its format in ``sources.normalizer``; new formats are added by writing a
function and decorating it with :func:`register_normalizer`, giving the
path the source serves a single credential at.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from urllib.parse import quote

from pydantic import BaseModel, Field


class CredentialStatus(StrEnum):
    """Lifecycle state of a credential as reported by its source."""

    ISSUED = "issued"
    REVOKED = "revoked"


class IssuerSummary(BaseModel):
    """Who issued a credential."""

    name: str | None = None
    did: str | None = None
    email: str | None = None
    logo_url: str | None = None
    description: str | None = None


class NormalizedCredential(BaseModel):
    """A credential in the connector's standard response format."""

    credential_id: str
    source_code: str
    status: CredentialStatus
    credential_unique_id: str | None = None
    title: str | None = None
    subject_name: str | None = None
    subject_logo_url: str | None = None
    holder_name: str | None = None
    issuer: IssuerSummary = Field(default_factory=IssuerSummary)
    issued_at: str | None = None
    valid_from: str | None = None
    valid_until: str | None = None
    fields: dict[str, Any] = Field(default_factory=dict)
    credential_url: str | None = None
    image_url: str | None = None
    qr_code_url: str | None = None
    hash: str | None = None
    credential_json: dict[str, Any] | None = None
    credential_json_content: str | None = Field(
        default=None,
        description=(
            "The credential document exactly as the source returned it. "
            "Proof checks must use this string, not a re-serialised "
            "credential_json."
        ),
    )


class NormalizationError(Exception):
    """Raised when a source's answer does not have the expected shape."""


Normalizer = Callable[[dict[str, Any], str, str], NormalizedCredential]


@dataclass(frozen=True, slots=True)
class SourceFormat:
    """How to fetch and read one credential from a kind of source.

    Attributes:
        credential_path: Path template with a ``{credential_id}``
            placeholder, relative to the source's base URL.
        normalize: Turns the decoded response into the standard format.
        verification_analytics_path: Path template where a verification
            of the credential is recorded, or None if the source has no
            such endpoint.
    """

    credential_path: str
    normalize: Normalizer
    verification_analytics_path: str | None = None

    def build_credential_path(self, credential_id: str) -> str:
        """Return the path for ``credential_id``."""
        return self.credential_path.format(
            credential_id=quote(credential_id, safe="")
        )

    def build_verification_analytics_path(
        self, credential_id: str
    ) -> str | None:
        """Return the analytics path for ``credential_id``, if any."""
        if self.verification_analytics_path is None:
            return None
        return self.verification_analytics_path.format(
            credential_id=quote(credential_id, safe="")
        )


_formats: dict[str, SourceFormat] = {}


def register_normalizer(
    name: str,
    credential_path: str,
    verification_analytics_path: str | None = None,
) -> Callable[[Normalizer], Normalizer]:
    """Register the decorated function as the format called ``name``."""

    def decorator(normalizer: Normalizer) -> Normalizer:
        if name in _formats:
            raise ValueError(f"normalizer {name!r} is already registered")
        _formats[name] = SourceFormat(
            credential_path, normalizer, verification_analytics_path
        )
        return normalizer

    return decorator


def get_source_format(name: str) -> SourceFormat:
    """Return the format registered as ``name``.

    Raises:
        KeyError: No normalizer has that name.
    """
    return _formats[name]


def is_normalizer_known(name: str) -> bool:
    """Return True if a normalizer is registered as ``name``."""
    return name in _formats

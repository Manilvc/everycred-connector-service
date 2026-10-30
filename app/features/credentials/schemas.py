"""Request and response models for credential lookups."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.normalizers.base import CredentialStatus, NormalizedCredential
from app.shared.identifiers import HolderEmail, Identifier


class HolderCredentialsLookup(BaseModel):
    """Ask for every credential issued to a holder.

    The email travels in the body, not the URL, so it does not end up in
    access logs.
    """

    model_config = ConfigDict(extra="forbid")

    holder_email: HolderEmail


class HolderCredentialGet(BaseModel):
    """Ask for one credential, only if it was issued to the holder."""

    model_config = ConfigDict(extra="forbid")

    holder_email: HolderEmail
    credential_id: Identifier


class HolderCredentialItem(BaseModel):
    """One of a holder's credentials, or why it could not be fetched."""

    source_code: str
    credential_id: str
    status: CredentialStatus
    first_seen_at: datetime = Field(
        description="When the source first reported the credential."
    )
    status_changed_at: datetime = Field(
        description=(
            "When the source last reported a change, e.g. the revocation."
        )
    )
    credential: NormalizedCredential | None = None
    error: str | None = Field(
        default=None,
        description="Set when the source could not supply the credential.",
    )


class HolderCredentialList(BaseModel):
    """Every credential the connector has routed to a holder."""

    items: list[HolderCredentialItem]


class SourceAnswer(BaseModel):
    """What the credential's source answered to a forwarded call."""

    source_code: str
    status_code: int
    ok: bool
    data: Any = None
    message: str | None = None

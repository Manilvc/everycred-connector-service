"""Request and response models for credential lookups."""

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
    credential: NormalizedCredential | None = None
    error: str | None = Field(
        default=None,
        description="Set when the source could not supply the credential.",
    )


class HolderCredentialList(BaseModel):
    """Every credential the connector has routed to a holder."""

    items: list[HolderCredentialItem]

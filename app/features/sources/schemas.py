"""Request and response models for sources."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
)

SOURCE_CODE_PATTERN = r"^[a-z0-9][a-z0-9-]{1,49}$"

SourceCode = Annotated[
    str, Field(pattern=SOURCE_CODE_PATTERN, examples=["dcs-india"])
]


def _check_base_url(base_url: AnyHttpUrl) -> AnyHttpUrl:
    if base_url.username or base_url.password:
        raise ValueError("base_url must not contain credentials")
    if base_url.query or base_url.fragment:
        raise ValueError("base_url must not have a query or fragment")
    return base_url


def normalise_base_url(base_url: AnyHttpUrl) -> str:
    """Return ``base_url`` as a string without a trailing slash."""
    return str(base_url).rstrip("/")


TENANT_ID_DESCRIPTION = (
    "Tenant uuid this source is, when several tenants share one DCS "
    "backend. Sent as the X-Tenant-ID header on every call so the DCS "
    "uses that tenant's database and connector API key."
)

TenantId = Annotated[
    str,
    Field(
        pattern=r"^[A-Za-z0-9-]{1,100}$",
        description=TENANT_ID_DESCRIPTION,
        examples=["01ARZ3NDEKTSV4RRFFQ69G5FAV"],
    ),
]


class SourceCreate(BaseModel):
    """Payload for registering a DCS instance."""

    model_config = ConfigDict(extra="forbid")

    code: SourceCode
    name: str = Field(min_length=1, max_length=150)
    base_url: AnyHttpUrl = Field(examples=["https://dcs-india.example.com"])
    tenant_id: TenantId | None = None
    api_key: SecretStr = Field(min_length=16, max_length=500)
    normalizer: str = Field(default="everycred_dcs", max_length=50)

    @field_validator("base_url")
    @classmethod
    def check_base_url(cls, base_url: AnyHttpUrl) -> AnyHttpUrl:
        """Reject URLs carrying credentials, query strings, or fragments."""
        return _check_base_url(base_url)


class SourceUpdate(BaseModel):
    """Fields an operator can change on an existing source."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=150)
    base_url: AnyHttpUrl | None = None
    # Send null to remove the tenant id; leave it out to keep it.
    tenant_id: TenantId | None = None
    api_key: SecretStr | None = Field(default=None, min_length=16)
    normalizer: str | None = Field(default=None, max_length=50)
    is_active: bool | None = None

    @field_validator("base_url")
    @classmethod
    def check_base_url(cls, base_url: AnyHttpUrl | None) -> AnyHttpUrl | None:
        """Apply the same URL rules as on creation."""
        if base_url is None:
            return None
        return _check_base_url(base_url)


class SourceResponse(BaseModel):
    """A source as shown to operators. Secrets are never included."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    base_url: str
    tenant_id: str | None
    normalizer: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class SourceWithSecretResponse(SourceResponse):
    """A source plus its webhook signing secret, returned only once."""

    webhook_secret: str = Field(
        description=(
            "Configure this in the DCS instance to sign its webhooks. It "
            "is shown only here; rotate it if it is lost."
        )
    )

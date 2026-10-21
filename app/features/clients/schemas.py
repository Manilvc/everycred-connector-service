"""Request and response models for clients."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.features.clients.models import ClientKind


class ClientCreate(BaseModel):
    """Payload for registering a client application."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=150)
    kind: ClientKind


class ClientResponse(BaseModel):
    """A client as shown to operators."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    kind: ClientKind
    key_prefix: str
    revoked_at: datetime | None
    created_at: datetime


class ClientWithKeyResponse(ClientResponse):
    """A new client plus its API key, returned only once."""

    api_key: str = Field(
        description=(
            "Send as X-API-Key. Only a hash is stored, so a lost key "
            "cannot be recovered; register a new client instead."
        )
    )

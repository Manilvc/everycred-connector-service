"""Webhook payloads sent by DCS sources, and the receipt returned."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.shared.identifiers import HolderEmail, Identifier


class EventType(StrEnum):
    """Events a DCS source reports to the connector."""

    CREDENTIAL_ISSUED = "credential.issued"
    CREDENTIAL_REVOKED = "credential.revoked"
    REQUEST_CREATED = "request.created"
    REQUEST_UPDATED = "request.updated"
    HOLDER_INVITED = "holder.invited"

    @property
    def is_credential_event(self) -> bool:
        """Return True for events about a credential."""
        return self in (
            EventType.CREDENTIAL_ISSUED,
            EventType.CREDENTIAL_REVOKED,
        )

    @property
    def is_request_event(self) -> bool:
        """Return True for events about a credential request."""
        return self in (EventType.REQUEST_CREATED, EventType.REQUEST_UPDATED)


class SourceEventData(BaseModel):
    """What the event is about."""

    model_config = ConfigDict(extra="ignore")

    credential_id: Identifier | None = None
    request_id: Identifier | None = None
    holder_email: HolderEmail | None = None
    status: str | None = Field(default=None, max_length=50)
    inviter_name: str | None = Field(
        default=None,
        max_length=200,
        description="Organisation that invited the holder (holder.invited).",
    )


class SourceEventPayload(BaseModel):
    """Body of a webhook from a DCS source."""

    model_config = ConfigDict(extra="ignore")

    id: Identifier
    event: EventType
    created_at: datetime
    data: SourceEventData

    @model_validator(mode="after")
    def check_required_ids(self) -> "SourceEventPayload":
        """Require the id that each event type is about."""
        if self.event.is_credential_event and not self.data.credential_id:
            raise ValueError("credential events need data.credential_id")
        if self.event.is_request_event and not self.data.request_id:
            raise ValueError("request events need data.request_id")
        if (
            self.event == EventType.HOLDER_INVITED
            and not self.data.holder_email
        ):
            raise ValueError("holder.invited needs data.holder_email")
        return self


class EventReceipt(BaseModel):
    """Acknowledgement returned to the source."""

    accepted: bool = True
    duplicate: bool = Field(
        description="True when this delivery id was already processed."
    )

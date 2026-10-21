"""ORM models for the routing table.

The connector keeps only what it needs to route: which source issued a
credential, and which sources know a holder. Credential contents are
never stored. Holders are identified by :func:`holder_key`, an HMAC of
their email, so the table cannot be read back into email addresses.
"""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.models import (
    TimestampMixin,
    UTCDateTime,
    UUIDPrimaryKeyMixin,
    utc_now,
)


class CredentialRoute(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Which source issued a credential, and its last known status."""

    __tablename__ = "credential_routes"

    credential_id: Mapped[str] = mapped_column(
        String(128), unique=True, index=True
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("sources.id", ondelete="CASCADE"), index=True
    )
    holder_key: Mapped[str | None] = mapped_column(
        String(64), index=True, default=None
    )
    status: Mapped[str] = mapped_column(String(20))
    last_event_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utc_now
    )


class HolderLink(UUIDPrimaryKeyMixin, Base):
    """Records that a source has sent events about a holder.

    Fan-out operations (such as listing a holder's requests) call only
    the sources linked to the holder.
    """

    __tablename__ = "holder_links"
    __table_args__ = (UniqueConstraint("holder_key", "source_id"),)

    holder_key: Mapped[str] = mapped_column(String(64), index=True)
    source_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("sources.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)

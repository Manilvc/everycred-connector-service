"""ORM model recording webhooks received from DCS sources."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.models import UTCDateTime, UUIDPrimaryKeyMixin, utc_now


class SourceEvent(UUIDPrimaryKeyMixin, Base):
    """One webhook delivery, kept so a retried delivery is applied once.

    Only identifiers are stored; the payload itself is not.
    """

    __tablename__ = "source_events"
    __table_args__ = (UniqueConstraint("source_id", "delivery_id"),)

    source_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("sources.id", ondelete="CASCADE")
    )
    delivery_id: Mapped[str] = mapped_column(String(128))
    event: Mapped[str] = mapped_column(String(50))
    received_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)

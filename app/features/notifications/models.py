"""ORM model for the outbox of events forwarded to the holder service."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.models import (
    TimestampMixin,
    UTCDateTime,
    UUIDPrimaryKeyMixin,
    enum_values,
    utc_now,
)


class NotificationStatus(StrEnum):
    """Delivery state of an outbox row."""

    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"


class HolderNotification(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One event waiting for, or finished with, delivery.

    The payload names the holder by email, so it is stored encrypted and
    cleared once the row is delivered or has failed for good.
    """

    __tablename__ = "holder_notifications"

    event: Mapped[str] = mapped_column(String(50))
    encrypted_payload: Mapped[str | None] = mapped_column(Text)
    status: Mapped[NotificationStatus] = mapped_column(
        Enum(
            NotificationStatus,
            native_enum=False,
            values_callable=enum_values,
            length=20,
        ),
        default=NotificationStatus.PENDING,
        index=True,
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utc_now, index=True
    )
    last_error: Mapped[str | None] = mapped_column(String(255))
    delivered_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

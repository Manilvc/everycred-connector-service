"""ORM model for applications that call the connector."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.models import (
    TimestampMixin,
    UTCDateTime,
    UUIDPrimaryKeyMixin,
    enum_values,
)


class ClientKind(StrEnum):
    """What a client is allowed to do.

    Verifiers may only look up a credential by its id. The holder
    service may also list a holder's credentials and run holder
    operations against DCS sources.
    """

    VERIFIER = "verifier"
    HOLDER_SERVICE = "holder_service"


class Client(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An application holding a connector API key.

    Only the key's prefix (for lookup) and its HMAC are stored.
    """

    __tablename__ = "clients"

    name: Mapped[str] = mapped_column(String(150))
    kind: Mapped[ClientKind] = mapped_column(
        Enum(
            ClientKind,
            native_enum=False,
            values_callable=enum_values,
            length=30,
        )
    )
    key_prefix: Mapped[str] = mapped_column(
        String(12), unique=True, index=True
    )
    key_hash: Mapped[str] = mapped_column(String(64))
    revoked_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime, default=None
    )

    @property
    def is_revoked(self) -> bool:
        """Return True once the client's key has been revoked."""
        return self.revoked_at is not None

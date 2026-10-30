"""ORM model for the DCS instances the connector routes to."""

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.models import TimestampMixin, UUIDPrimaryKeyMixin


class Source(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One DCS deployment, such as DCS-India or DCS-Education.

    The API key the connector sends to the source and the secret the
    source signs its webhooks with are both needed in plain text at run
    time, so they are stored Fernet-encrypted rather than hashed.

    ``tenant_origin`` is set when the source is one tenant of a shared
    DCS backend: the DCS picks the tenant from the request's ``Origin``,
    so every call to the source carries it.
    """

    __tablename__ = "sources"

    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(150))
    base_url: Mapped[str] = mapped_column(String(500))
    tenant_origin: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    normalizer: Mapped[str] = mapped_column(String(50))
    encrypted_api_key: Mapped[str] = mapped_column(Text)
    encrypted_webhook_secret: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

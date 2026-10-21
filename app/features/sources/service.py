"""Registration and maintenance of DCS sources."""

import logging
import secrets

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.encryption import decrypt_text, encrypt_text
from app.core.exceptions import AppError
from app.features.sources.exceptions import (
    SourceCodeTakenError,
    SourceNotFoundError,
)
from app.features.sources.models import Source
from app.features.sources.repository import SourceRepository
from app.features.sources.schemas import (
    SourceCreate,
    SourceUpdate,
    normalise_base_url,
)
from app.normalizers.base import is_normalizer_known

logger = logging.getLogger(__name__)

WEBHOOK_SECRET_PREFIX = "whsec_"  # noqa: S105 - a label, not a secret


class UnknownNormalizerError(AppError):
    """Raised when a source names a normalizer that does not exist."""

    error_code = "unknown_normalizer"


def _generate_webhook_secret() -> str:
    return f"{WEBHOOK_SECRET_PREFIX}{secrets.token_urlsafe(32)}"


def _check_normalizer(name: str) -> None:
    if not is_normalizer_known(name):
        raise UnknownNormalizerError(f"Normalizer {name!r} does not exist.")


class SourceService:
    """Creates, updates, and looks up sources for operators.

    Attributes:
        session: Unit of work the service commits.
        repository: Persistence for sources.
        settings: Source of the encryption keys.
    """

    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.repository = SourceRepository(session)
        self.settings = settings

    async def create_source(self, payload: SourceCreate) -> tuple[Source, str]:
        """Register a source and return it with its new webhook secret.

        Raises:
            SourceCodeTakenError: Another source already uses the code.
            UnknownNormalizerError: The normalizer is not registered.
        """
        _check_normalizer(payload.normalizer)
        if await self.repository.get_by_code(payload.code) is not None:
            raise SourceCodeTakenError(
                f"Source code {payload.code} is already in use."
            )
        webhook_secret = _generate_webhook_secret()
        source = Source(
            code=payload.code,
            name=payload.name,
            base_url=normalise_base_url(payload.base_url),
            normalizer=payload.normalizer,
            encrypted_api_key=encrypt_text(
                payload.api_key.get_secret_value(), self.settings
            ),
            encrypted_webhook_secret=encrypt_text(
                webhook_secret, self.settings
            ),
            is_active=True,
        )
        self.repository.add(source)
        await self.session.commit()
        logger.info("Registered source %s", source.code)
        return source, webhook_secret

    async def get_source(self, code: str) -> Source:
        """Return the source with ``code``.

        Raises:
            SourceNotFoundError: No source has that code.
        """
        source = await self.repository.get_by_code(code)
        if source is None:
            raise SourceNotFoundError(f"Source {code} does not exist.")
        return source

    async def list_sources(
        self, limit: int, offset: int
    ) -> tuple[list[Source], int]:
        """Return one page of sources and the total count."""
        sources = await self.repository.list_page(limit, offset)
        return sources, await self.repository.count()

    async def update_source(self, code: str, payload: SourceUpdate) -> Source:
        """Apply the fields set in ``payload`` to the source.

        Raises:
            SourceNotFoundError: No source has that code.
            UnknownNormalizerError: The new normalizer is not registered.
        """
        source = await self.get_source(code)
        if payload.name is not None:
            source.name = payload.name
        if payload.base_url is not None:
            source.base_url = normalise_base_url(payload.base_url)
        if payload.api_key is not None:
            source.encrypted_api_key = encrypt_text(
                payload.api_key.get_secret_value(), self.settings
            )
        if payload.normalizer is not None:
            _check_normalizer(payload.normalizer)
            source.normalizer = payload.normalizer
        if payload.is_active is not None:
            source.is_active = payload.is_active
        await self.session.commit()
        logger.info("Updated source %s", source.code)
        return source

    async def rotate_webhook_secret(self, code: str) -> tuple[Source, str]:
        """Replace the source's webhook secret and return the new one.

        The old secret stops working immediately, so the DCS must be
        updated with the new value straight away.

        Raises:
            SourceNotFoundError: No source has that code.
        """
        source = await self.get_source(code)
        webhook_secret = _generate_webhook_secret()
        source.encrypted_webhook_secret = encrypt_text(
            webhook_secret, self.settings
        )
        await self.session.commit()
        logger.warning("Rotated webhook secret of source %s", source.code)
        return source, webhook_secret

    def read_webhook_secret(self, source: Source) -> str:
        """Return the source's webhook secret in plain text."""
        return decrypt_text(source.encrypted_webhook_secret, self.settings)

"""Registration, revocation, and authentication of client applications."""

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import AuthenticationError
from app.core.models import utc_now
from app.core.security import (
    extract_api_key_prefix,
    generate_api_key,
    is_api_key_valid,
)
from app.features.clients.exceptions import ClientNotFoundError
from app.features.clients.models import Client
from app.features.clients.repository import ClientRepository
from app.features.clients.schemas import ClientCreate

logger = logging.getLogger(__name__)

_INVALID_KEY_MESSAGE = "A valid X-API-Key header is required."


class ClientService:
    """Manages client applications and checks their API keys.

    Attributes:
        session: Unit of work the service commits.
        repository: Persistence for clients.
        settings: Source of the API key HMAC secret.
    """

    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.repository = ClientRepository(session)
        self.settings = settings

    async def create_client(self, payload: ClientCreate) -> tuple[Client, str]:
        """Register a client and return it with its plaintext API key."""
        generated_key = generate_api_key(self.settings)
        client = Client(
            name=payload.name,
            kind=payload.kind,
            key_prefix=generated_key.prefix,
            key_hash=generated_key.key_hash,
        )
        self.repository.add(client)
        await self.session.commit()
        logger.info("Registered %s client %s", client.kind, client.id)
        return client, generated_key.plaintext

    async def list_clients(
        self, limit: int, offset: int
    ) -> tuple[list[Client], int]:
        """Return one page of clients and the total count."""
        clients = await self.repository.list_page(limit, offset)
        return clients, await self.repository.count()

    async def revoke_client(self, client_id: uuid.UUID) -> Client:
        """Revoke a client's key. Revoking twice keeps the first time.

        Raises:
            ClientNotFoundError: No client has that id.
        """
        client = await self.repository.get(client_id)
        if client is None:
            raise ClientNotFoundError(f"Client {client_id} does not exist.")
        if client.revoked_at is None:
            client.revoked_at = utc_now()
            await self.session.commit()
            logger.warning("Revoked client %s", client.id)
        return client

    async def authenticate(self, api_key: str | None) -> Client:
        """Return the active client that owns ``api_key``.

        Raises:
            AuthenticationError: The key is missing, malformed, unknown,
                wrong, or revoked. The reason is not revealed.
        """
        key_prefix = extract_api_key_prefix(api_key) if api_key else None
        if api_key is None or key_prefix is None:
            raise AuthenticationError(_INVALID_KEY_MESSAGE)
        client = await self.repository.get_by_key_prefix(key_prefix)
        if (
            client is None
            or client.is_revoked
            or not is_api_key_valid(api_key, client.key_hash, self.settings)
        ):
            raise AuthenticationError(_INVALID_KEY_MESSAGE)
        return client

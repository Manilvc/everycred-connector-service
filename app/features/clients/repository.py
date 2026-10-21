"""Database access for clients."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.clients.models import Client


class ClientRepository:
    """Queries and persistence for :class:`Client` rows."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, client_id: uuid.UUID) -> Client | None:
        """Return the client with ``client_id``, or None."""
        return await self.session.get(Client, client_id)

    async def get_by_key_prefix(self, key_prefix: str) -> Client | None:
        """Return the client whose key has ``key_prefix``, or None."""
        return await self.session.scalar(
            select(Client).where(Client.key_prefix == key_prefix)
        )

    async def list_page(self, limit: int, offset: int) -> list[Client]:
        """Return one page of clients, newest first."""
        result = await self.session.scalars(
            select(Client)
            .order_by(Client.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result)

    async def count(self) -> int:
        """Return the number of clients."""
        return await self.session.scalar(select(func.count(Client.id))) or 0

    def add(self, client: Client) -> None:
        """Stage a new client for insertion."""
        self.session.add(client)

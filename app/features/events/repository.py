"""Database access for received webhook deliveries."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.events.models import SourceEvent


class SourceEventRepository:
    """Queries and persistence for :class:`SourceEvent` rows."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def exists(self, source_id: uuid.UUID, delivery_id: str) -> bool:
        """Return True if the source's delivery was already recorded."""
        event_id = await self.session.scalar(
            select(SourceEvent.id).where(
                SourceEvent.source_id == source_id,
                SourceEvent.delivery_id == delivery_id,
            )
        )
        return event_id is not None

    def add(self, event: SourceEvent) -> None:
        """Stage a received delivery for insertion."""
        self.session.add(event)

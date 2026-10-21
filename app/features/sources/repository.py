"""Database access for sources."""

import uuid
from collections.abc import Collection

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.sources.models import Source


class SourceRepository:
    """Queries and persistence for :class:`Source` rows."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_code(self, code: str) -> Source | None:
        """Return the source with ``code``, or None."""
        return await self.session.scalar(
            select(Source).where(Source.code == code)
        )

    async def list_by_ids(
        self, source_ids: Collection[uuid.UUID]
    ) -> list[Source]:
        """Return the sources whose ids are in ``source_ids``."""
        if not source_ids:
            return []
        result = await self.session.scalars(
            select(Source).where(Source.id.in_(source_ids))
        )
        return list(result)

    async def list_page(self, limit: int, offset: int) -> list[Source]:
        """Return one page of sources ordered by code."""
        result = await self.session.scalars(
            select(Source).order_by(Source.code).limit(limit).offset(offset)
        )
        return list(result)

    async def count(self) -> int:
        """Return the number of sources."""
        return await self.session.scalar(select(func.count(Source.id))) or 0

    def add(self, source: Source) -> None:
        """Stage a new source for insertion."""
        self.session.add(source)

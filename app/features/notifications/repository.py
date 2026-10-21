"""Database access for the holder notification outbox."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.notifications.models import (
    HolderNotification,
    NotificationStatus,
)


class NotificationRepository:
    """Queries and persistence for :class:`HolderNotification` rows."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, notification: HolderNotification) -> None:
        """Stage a new outbox row for insertion."""
        self.session.add(notification)

    async def list_due(
        self, now: datetime, limit: int
    ) -> list[HolderNotification]:
        """Return pending rows whose next attempt is due, oldest first."""
        result = await self.session.scalars(
            select(HolderNotification)
            .where(
                HolderNotification.status == NotificationStatus.PENDING,
                HolderNotification.next_attempt_at <= now,
            )
            .order_by(HolderNotification.next_attempt_at)
            .limit(limit)
        )
        return list(result)

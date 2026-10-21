"""Database access for credential routes and holder links."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import utc_now
from app.features.routing.models import CredentialRoute, HolderLink


class RoutingRepository:
    """Queries and persistence for the routing table."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_route(self, credential_id: str) -> CredentialRoute | None:
        """Return the route for ``credential_id``, or None."""
        return await self.session.scalar(
            select(CredentialRoute).where(
                CredentialRoute.credential_id == credential_id
            )
        )

    async def list_routes_for_holder(
        self, holder_key: str, limit: int
    ) -> list[CredentialRoute]:
        """Return up to ``limit`` of a holder's routes, newest first."""
        result = await self.session.scalars(
            select(CredentialRoute)
            .where(CredentialRoute.holder_key == holder_key)
            .order_by(CredentialRoute.last_event_at.desc())
            .limit(limit)
        )
        return list(result)

    async def list_linked_source_ids(self, holder_key: str) -> list[uuid.UUID]:
        """Return the ids of every source linked to the holder."""
        result = await self.session.scalars(
            select(HolderLink.source_id).where(
                HolderLink.holder_key == holder_key
            )
        )
        return list(result)

    async def is_holder_linked(
        self, holder_key: str, source_id: uuid.UUID
    ) -> bool:
        """Return True if the source has sent events about the holder."""
        link_id = await self.session.scalar(
            select(HolderLink.id).where(
                HolderLink.holder_key == holder_key,
                HolderLink.source_id == source_id,
            )
        )
        return link_id is not None

    async def save_route(
        self,
        credential_id: str,
        source_id: uuid.UUID,
        holder_key: str | None,
        status: str,
    ) -> CredentialRoute:
        """Create the route or update its status and holder.

        A route's source never changes; callers check that before
        saving (see ``EventService``).
        """
        route = await self.get_route(credential_id)
        if route is None:
            route = CredentialRoute(
                credential_id=credential_id,
                source_id=source_id,
                holder_key=holder_key,
                status=status,
            )
            self.session.add(route)
            return route
        route.status = status
        route.last_event_at = utc_now()
        if holder_key is not None:
            route.holder_key = holder_key
        return route

    async def link_holder(self, holder_key: str, source_id: uuid.UUID) -> None:
        """Link the holder to the source unless already linked."""
        if not await self.is_holder_linked(holder_key, source_id):
            self.session.add(
                HolderLink(holder_key=holder_key, source_id=source_id)
            )

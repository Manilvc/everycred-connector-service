"""Credential lookups: routing, calling the source, and normalizing.

This is the query path of the connector. A credential id is looked up in
the routing table to find its source, the source is called through
:class:`SourceCaller`, and the answer is turned into the standard format
by the source's normalizer. Nothing fetched is stored.
"""

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import AppError
from app.features.credentials.exceptions import (
    CredentialNotFoundError,
    InvalidSourceResponseError,
)
from app.features.credentials.schemas import (
    HolderCredentialItem,
    HolderCredentialList,
)
from app.features.routing.holder_keys import holder_key
from app.features.routing.models import CredentialRoute
from app.features.routing.repository import RoutingRepository
from app.features.sources.caller import SourceCaller
from app.features.sources.exceptions import SourceUnavailableError
from app.features.sources.models import Source
from app.features.sources.repository import SourceRepository
from app.normalizers.base import (
    CredentialStatus,
    NormalizationError,
    NormalizedCredential,
    get_source_format,
)

logger = logging.getLogger(__name__)

# Upper bound on credentials fetched for one holder lookup, so a single
# request cannot fan out into thousands of source calls.
MAX_HOLDER_CREDENTIALS = 200


class CredentialService:
    """Finds a credential's source and fetches it in the standard format.

    Attributes:
        routing: Read access to the routing table.
        sources: Read access to sources.
        caller: Sends requests to sources.
        settings: Holder key secret and fan-out limit.
    """

    def __init__(
        self,
        session: AsyncSession,
        caller: SourceCaller,
        settings: Settings,
    ) -> None:
        self.routing = RoutingRepository(session)
        self.sources = SourceRepository(session)
        self.caller = caller
        self.settings = settings

    async def get_credential(self, credential_id: str) -> NormalizedCredential:
        """Return a credential by id, for verifier applications.

        Raises:
            CredentialNotFoundError: No route exists, or the source does
                not know the credential.
            SourceUnavailableError: The source failed or is unreachable.
            InvalidSourceResponseError: The answer could not be read.
        """
        route = await self.routing.get_route(credential_id)
        if route is None:
            raise CredentialNotFoundError(
                f"Credential {credential_id} is not known to the connector."
            )
        source = await self._get_route_source(route)
        return await self._fetch(source, credential_id)

    async def get_holder_credential(
        self, holder_email: str, credential_id: str
    ) -> NormalizedCredential:
        """Return a credential only if it was issued to the holder.

        A credential belonging to someone else is reported as not found,
        so the holder service cannot probe for other holders' ids.

        Raises:
            CredentialNotFoundError: Unknown, or not the holder's.
            SourceUnavailableError: The source failed or is unreachable.
            InvalidSourceResponseError: The answer could not be read.
        """
        route = await self.routing.get_route(credential_id)
        if route is None or route.holder_key != holder_key(
            holder_email, self.settings
        ):
            raise CredentialNotFoundError(
                f"Credential {credential_id} was not found for this holder."
            )
        source = await self._get_route_source(route)
        return await self._fetch(source, credential_id)

    async def list_holder_credentials(
        self, holder_email: str
    ) -> HolderCredentialList:
        """Fetch every credential routed to the holder, concurrently.

        A failure at one source does not fail the whole lookup; the
        affected items carry an ``error`` instead of a credential.
        """
        routes = await self.routing.list_routes_for_holder(
            holder_key(holder_email, self.settings), MAX_HOLDER_CREDENTIALS
        )
        sources = await self.sources.list_by_ids(
            {route.source_id for route in routes}
        )
        source_by_id = {source.id: source for source in sources}
        limiter = asyncio.Semaphore(self.settings.source_max_concurrent_calls)

        async def fetch_item(route: CredentialRoute) -> HolderCredentialItem:
            source = source_by_id[route.source_id]
            item = HolderCredentialItem(
                source_code=source.code,
                credential_id=route.credential_id,
                status=CredentialStatus(route.status),
            )
            async with limiter:
                try:
                    item.credential = await self._fetch(
                        source, route.credential_id
                    )
                except AppError as exc:
                    item.error = exc.message
            return item

        items = await asyncio.gather(*(fetch_item(r) for r in routes))
        return HolderCredentialList(items=list(items))

    async def _get_route_source(self, route: CredentialRoute) -> Source:
        sources = await self.sources.list_by_ids({route.source_id})
        if not sources:
            # Sources are not deletable through the API, so this means the
            # row was removed by hand.
            raise CredentialNotFoundError(
                f"Credential {route.credential_id} has no source."
            )
        return sources[0]

    async def _fetch(
        self, source: Source, credential_id: str
    ) -> NormalizedCredential:
        source_format = get_source_format(source.normalizer)
        response = await self.caller.call(
            source, "GET", source_format.build_credential_path(credential_id)
        )
        if response.status_code == 404:
            raise CredentialNotFoundError(
                f"Source {source.code} does not know credential "
                f"{credential_id}."
            )
        if not response.is_success or not isinstance(response.body, dict):
            logger.warning(
                "Source %s answered %s for credential %s",
                source.code,
                response.status_code,
                credential_id,
            )
            raise SourceUnavailableError(
                f"Source {source.code} could not return the credential."
            )
        try:
            return source_format.normalize(
                response.body, credential_id, source.code
            )
        except (NormalizationError, ValueError) as exc:
            logger.warning(
                "Could not normalize credential %s from %s: %s",
                credential_id,
                source.code,
                exc,
            )
            raise InvalidSourceResponseError(
                f"Source {source.code} returned an unexpected format."
            ) from exc

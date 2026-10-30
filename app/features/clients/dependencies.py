"""Dependency providers for the clients feature.

Routes declare who may call them with :data:`CurrentClient` (any active
client) or :data:`CurrentHolderService` (holder service clients only).
"""

from typing import Annotated

from fastapi import Depends, Security
from fastapi.security import APIKeyHeader

from app.core.config import SettingsDep
from app.core.database import DbSession
from app.core.exceptions import PermissionDeniedError
from app.features.clients.models import Client, ClientKind
from app.features.clients.service import ClientService

_api_key_header = APIKeyHeader(
    name="X-API-Key", scheme_name="ClientKey", auto_error=False
)


def get_client_service(
    session: DbSession, settings: SettingsDep
) -> ClientService:
    """Build a client service bound to the request's session."""
    return ClientService(session, settings)


ClientServiceDep = Annotated[ClientService, Depends(get_client_service)]


async def get_current_client(
    service: ClientServiceDep,
    api_key: Annotated[str | None, Security(_api_key_header)],
) -> Client:
    """Return the client authenticated by the ``X-API-Key`` header."""
    return await service.authenticate(api_key)


CurrentClient = Annotated[Client, Depends(get_current_client)]


def require_holder_service(client: CurrentClient) -> Client:
    """Allow only holder service clients.

    Raises:
        PermissionDeniedError: The client is a verifier.
    """
    if client.kind is not ClientKind.HOLDER_SERVICE:
        raise PermissionDeniedError(
            "This endpoint is available to the holder service only."
        )
    return client


CurrentHolderService = Annotated[Client, Depends(require_holder_service)]

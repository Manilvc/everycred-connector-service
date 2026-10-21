"""Operator routes for registering and revoking client applications."""

import uuid

from fastapi import APIRouter, status

from app.core.security import AdminOnly
from app.features.clients.dependencies import ClientServiceDep
from app.features.clients.schemas import (
    ClientCreate,
    ClientResponse,
    ClientWithKeyResponse,
)
from app.shared.pagination import Pagination
from app.shared.schemas import ErrorResponse, Page

router = APIRouter(
    prefix="/clients",
    tags=["Clients"],
    dependencies=[AdminOnly],
    responses={status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse}},
)


@router.post(
    "",
    response_model=ClientWithKeyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a client application",
)
async def create_client(
    payload: ClientCreate, service: ClientServiceDep
) -> ClientWithKeyResponse:
    """Register a verifier or the holder service and issue its API key."""
    client, api_key = await service.create_client(payload)
    return ClientWithKeyResponse.model_validate(
        {
            **ClientResponse.model_validate(client).model_dump(),
            "api_key": api_key,
        }
    )


@router.get(
    "",
    response_model=Page[ClientResponse],
    summary="List client applications",
)
async def list_clients(
    pagination: Pagination, service: ClientServiceDep
) -> Page[ClientResponse]:
    """Return one page of clients, newest first."""
    clients, total = await service.list_clients(
        pagination.limit, pagination.offset
    )
    return Page[ClientResponse](
        items=[ClientResponse.model_validate(client) for client in clients],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.post(
    "/{client_id}/revoke",
    response_model=ClientResponse,
    summary="Revoke a client's API key",
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}},
)
async def revoke_client(
    client_id: uuid.UUID, service: ClientServiceDep
) -> ClientResponse:
    """Revoke the client's key; later calls with it are rejected."""
    return ClientResponse.model_validate(
        await service.revoke_client(client_id)
    )

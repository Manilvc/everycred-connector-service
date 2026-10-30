"""Credential lookups for verifier applications and the holder service."""

from typing import Annotated, Any

from fastapi import APIRouter, Body, Path, status

from app.features.clients.dependencies import (
    CurrentClient,
    CurrentHolderService,
)
from app.features.credentials.dependencies import CredentialServiceDep
from app.features.credentials.schemas import (
    HolderCredentialGet,
    HolderCredentialList,
    HolderCredentialsLookup,
    SourceAnswer,
)
from app.normalizers.base import NormalizedCredential
from app.shared.identifiers import IDENTIFIER_PATTERN
from app.shared.schemas import ErrorResponse

_AUTH_ERRORS = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
    status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
}
_LOOKUP_ERRORS = {
    **_AUTH_ERRORS,
    status.HTTP_404_NOT_FOUND: {
        "model": ErrorResponse,
        "description": "Credential not found",
    },
    status.HTTP_502_BAD_GATEWAY: {
        "model": ErrorResponse,
        "description": "The source failed or returned an unreadable answer",
    },
}

router = APIRouter(tags=["Credentials"])


@router.get(
    "/credentials/{credential_id}",
    response_model=NormalizedCredential,
    summary="Get a credential by id",
    responses=_LOOKUP_ERRORS,
)
async def get_credential(
    credential_id: Annotated[str, Path(pattern=IDENTIFIER_PATTERN)],
    service: CredentialServiceDep,
    client: CurrentClient,
) -> NormalizedCredential:
    """Route the id to its DCS source and return the standard response."""
    return await service.get_credential(credential_id)


@router.post(
    "/holders/credentials/lookup",
    response_model=HolderCredentialList,
    summary="List a holder's credentials",
    responses=_AUTH_ERRORS,
)
async def list_holder_credentials(
    payload: HolderCredentialsLookup,
    service: CredentialServiceDep,
    client: CurrentHolderService,
) -> HolderCredentialList:
    """Fetch every credential issued to the holder, from all sources."""
    return await service.list_holder_credentials(payload.holder_email)


@router.post(
    "/holders/credentials/get",
    response_model=NormalizedCredential,
    summary="Get one of a holder's credentials",
    responses=_LOOKUP_ERRORS,
)
async def get_holder_credential(
    payload: HolderCredentialGet,
    service: CredentialServiceDep,
    client: CurrentHolderService,
) -> NormalizedCredential:
    """Return the credential only if it was issued to the holder."""
    return await service.get_holder_credential(
        payload.holder_email, payload.credential_id
    )


@router.post(
    "/credentials/{credential_id}/verification-analytics",
    response_model=SourceAnswer,
    summary="Record a verification of a credential",
    responses=_LOOKUP_ERRORS,
)
async def record_verification(
    credential_id: Annotated[str, Path(pattern=IDENTIFIER_PATTERN)],
    record: Annotated[dict[str, Any], Body()],
    service: CredentialServiceDep,
    client: CurrentClient,
) -> SourceAnswer:
    """Forward a verification record to the credential's DCS source.

    The record (``verification_status``, ``stage``, ``reason``) is passed
    through unchanged, and the source's answer is returned with its own
    status code, so wallets keep the DCS behaviour.
    """
    return await service.record_verification(credential_id, record)

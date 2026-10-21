"""Holder operations forwarded to DCS sources for the holder service."""

from fastapi import APIRouter, status

from app.features.clients.dependencies import CurrentHolderService
from app.features.operations.dependencies import OperationServiceDep
from app.features.operations.schemas import (
    HolderOperationRequest,
    HolderOperationResponse,
)
from app.shared.schemas import ErrorResponse

router = APIRouter(prefix="/holders", tags=["Holder Operations"])


@router.post(
    "/operations",
    response_model=HolderOperationResponse,
    summary="Run a holder operation on DCS sources",
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "model": ErrorResponse,
            "description": (
                "unknown_operation, invalid_params, source_required, or "
                "source_inactive"
            ),
        },
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "source_not_found or holder_not_linked",
        },
    },
)
async def run_holder_operation(
    payload: HolderOperationRequest,
    service: OperationServiceDep,
    client: CurrentHolderService,
) -> HolderOperationResponse:
    """Forward a named operation to one source, or fan out to all.

    Each source's answer is returned with its own status code; a failing
    source does not fail the whole call.
    """
    return await service.run(payload)

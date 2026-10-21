"""Versioned API router that collects every feature's routes.

Each feature exposes its own ``APIRouter``; this module is the single
place where they are mounted under ``/v1``.
"""

from fastapi import APIRouter, status

from app.features.clients.router import router as clients_router
from app.features.credentials.router import router as credentials_router
from app.features.events.router import router as events_router
from app.features.operations.router import router as operations_router
from app.features.sources.router import router as sources_router
from app.shared.schemas import ErrorResponse

api_v1_router = APIRouter(
    prefix="/v1",
    # Documented once here so every versioned route shows the shared
    # error envelope in OpenAPI.
    responses={
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
)

api_v1_router.include_router(sources_router)
api_v1_router.include_router(clients_router)
api_v1_router.include_router(events_router)
api_v1_router.include_router(credentials_router)
api_v1_router.include_router(operations_router)

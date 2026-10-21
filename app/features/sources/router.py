"""Operator routes for registering and maintaining DCS sources."""

from typing import Annotated

from fastapi import APIRouter, Path, status

from app.core.security import AdminOnly
from app.features.sources.dependencies import SourceServiceDep
from app.features.sources.models import Source
from app.features.sources.schemas import (
    SOURCE_CODE_PATTERN,
    SourceCreate,
    SourceResponse,
    SourceUpdate,
    SourceWithSecretResponse,
)
from app.shared.pagination import Pagination
from app.shared.schemas import ErrorResponse, Page

router = APIRouter(
    prefix="/sources",
    tags=["Sources"],
    dependencies=[AdminOnly],
    responses={status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse}},
)

SourceCodePath = Annotated[
    str, Path(pattern=SOURCE_CODE_PATTERN, examples=["dcs-india"])
]

_NOT_FOUND = {
    status.HTTP_404_NOT_FOUND: {
        "model": ErrorResponse,
        "description": "Source not found",
    }
}


def _with_secret(
    source: Source, webhook_secret: str
) -> SourceWithSecretResponse:
    return SourceWithSecretResponse.model_validate(
        {
            **SourceResponse.model_validate(source).model_dump(),
            "webhook_secret": webhook_secret,
        }
    )


@router.post(
    "",
    response_model=SourceWithSecretResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a DCS source",
    responses={status.HTTP_409_CONFLICT: {"model": ErrorResponse}},
)
async def create_source(
    payload: SourceCreate, service: SourceServiceDep
) -> SourceWithSecretResponse:
    """Register a DCS instance and return its webhook signing secret."""
    source, webhook_secret = await service.create_source(payload)
    return _with_secret(source, webhook_secret)


@router.get(
    "",
    response_model=Page[SourceResponse],
    summary="List DCS sources",
)
async def list_sources(
    pagination: Pagination, service: SourceServiceDep
) -> Page[SourceResponse]:
    """Return one page of registered sources."""
    sources, total = await service.list_sources(
        pagination.limit, pagination.offset
    )
    return Page[SourceResponse](
        items=[SourceResponse.model_validate(source) for source in sources],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get(
    "/{source_code}",
    response_model=SourceResponse,
    summary="Get a DCS source",
    responses=_NOT_FOUND,
)
async def get_source(
    source_code: SourceCodePath, service: SourceServiceDep
) -> SourceResponse:
    """Return one source by its code."""
    return SourceResponse.model_validate(await service.get_source(source_code))


@router.patch(
    "/{source_code}",
    response_model=SourceResponse,
    summary="Update a DCS source",
    responses=_NOT_FOUND,
)
async def update_source(
    source_code: SourceCodePath,
    payload: SourceUpdate,
    service: SourceServiceDep,
) -> SourceResponse:
    """Change a source's name, URL, API key, normalizer, or status."""
    source = await service.update_source(source_code, payload)
    return SourceResponse.model_validate(source)


@router.post(
    "/{source_code}/webhook-secret",
    response_model=SourceWithSecretResponse,
    summary="Rotate a source's webhook secret",
    responses=_NOT_FOUND,
)
async def rotate_webhook_secret(
    source_code: SourceCodePath, service: SourceServiceDep
) -> SourceWithSecretResponse:
    """Issue a new webhook secret; the old one stops working at once."""
    source, webhook_secret = await service.rotate_webhook_secret(source_code)
    return _with_secret(source, webhook_secret)

"""Webhook endpoint DCS sources call when a credential or request changes."""

from typing import Annotated

from fastapi import APIRouter, Header, Path, Request, status

from app.core.signatures import DELIVERY_HEADER, SIGNATURE_HEADER
from app.features.events.dependencies import EventServiceDep
from app.features.events.exceptions import PayloadTooLargeError
from app.features.events.schemas import EventReceipt
from app.features.sources.schemas import SOURCE_CODE_PATTERN
from app.shared.identifiers import IDENTIFIER_PATTERN
from app.shared.schemas import ErrorResponse

# Events carry identifiers only; anything near this size is not one.
MAX_EVENT_BODY_BYTES = 64 * 1024

router = APIRouter(prefix="/sources", tags=["Source Events"])


async def _read_limited_body(request: Request) -> bytes:
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_EVENT_BODY_BYTES:
            raise PayloadTooLargeError("The event body is too large.")
    return bytes(body)


@router.post(
    "/{source_code}/events",
    response_model=EventReceipt,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Receive an event from a DCS source",
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "model": ErrorResponse,
            "description": "Signature missing, wrong, or too old",
        },
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
        status.HTTP_413_CONTENT_TOO_LARGE: {"model": ErrorResponse},
    },
)
async def receive_source_event(
    request: Request,
    source_code: Annotated[str, Path(pattern=SOURCE_CODE_PATTERN)],
    service: EventServiceDep,
    signature: Annotated[
        str | None, Header(alias=SIGNATURE_HEADER, max_length=200)
    ] = None,
    delivery_id: Annotated[
        str | None,
        Header(alias=DELIVERY_HEADER, pattern=IDENTIFIER_PATTERN),
    ] = None,
) -> EventReceipt:
    """Apply a signed credential or request event from a DCS source.

    The body is read raw because the signature covers the exact bytes
    sent. Retried deliveries with the same delivery id are acknowledged
    without being applied again.
    """
    raw_body = await _read_limited_body(request)
    return await service.receive(source_code, raw_body, signature, delivery_id)

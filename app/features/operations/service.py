"""Forwarding of holder operations to DCS sources.

The holder service owns the holder's identity; everything about requests,
submissions, workflows, and KYC still lives in the DCS that issued them.
This service picks the right source (or every linked source, for list
operations), calls its internal holder API, and passes the answers back
without storing them.
"""

import asyncio
import json
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.features.operations.catalog import OPERATIONS_BY_NAME, HolderOperation
from app.features.operations.exceptions import (
    HolderNotLinkedError,
    InvalidOperationParamsError,
    SourceRequiredError,
    UnknownOperationError,
)
from app.features.operations.schemas import (
    HolderOperationRequest,
    HolderOperationResponse,
    OperationResult,
)
from app.features.routing.holder_keys import holder_key, normalise_email
from app.features.routing.repository import RoutingRepository
from app.features.sources.caller import SourceCaller
from app.features.sources.exceptions import (
    SourceInactiveError,
    SourceNotFoundError,
    SourceUnavailableError,
)
from app.features.sources.models import Source
from app.features.sources.repository import SourceRepository

logger = logging.getLogger(__name__)

# Submissions carry form data, not files; anything larger is refused.
MAX_BODY_BYTES = 256 * 1024


def _check_request(
    operation: HolderOperation, request: HolderOperationRequest
) -> None:
    if set(request.params) != set(operation.param_names):
        raise InvalidOperationParamsError(
            f"Operation {operation.name} takes params "
            f"{sorted(operation.param_names)}."
        )
    if request.body is not None and not operation.has_body:
        raise InvalidOperationParamsError(
            f"Operation {operation.name} does not take a body."
        )
    if (
        request.body is not None
        and len(json.dumps(request.body)) > MAX_BODY_BYTES
    ):
        raise InvalidOperationParamsError("The body is too large.")
    if request.source_code is None and not operation.is_fan_out:
        raise SourceRequiredError(
            f"Operation {operation.name} needs a source_code."
        )


def _to_result(source: Source, status_code: int, body: Any) -> OperationResult:
    # DCS answers with {"status", "data", "message"}; unwrap it so the
    # holder service gets the data and the message side by side.
    if isinstance(body, dict) and "data" in body:
        message = body.get("message")
        return OperationResult(
            source_code=source.code,
            status_code=status_code,
            ok=200 <= status_code < 300,
            data=body["data"],
            message=message if isinstance(message, str) else None,
        )
    return OperationResult(
        source_code=source.code,
        status_code=status_code,
        ok=200 <= status_code < 300,
        data=body,
    )


class OperationService:
    """Runs catalog operations against the holder's DCS sources.

    Attributes:
        routing: Read access to holder links.
        sources: Read access to sources.
        caller: Sends requests to sources.
        settings: Holder key secret and concurrency limit.
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

    async def run(
        self, request: HolderOperationRequest
    ) -> HolderOperationResponse:
        """Validate the request, call the sources, and collect answers.

        Raises:
            UnknownOperationError: The operation is not in the catalog.
            InvalidOperationParamsError: Params or body do not fit it.
            SourceRequiredError: An item operation has no source_code.
            SourceNotFoundError: The named source does not exist.
            SourceInactiveError: The named source is switched off.
            HolderNotLinkedError: The source never reported the holder.
        """
        operation = OPERATIONS_BY_NAME.get(request.operation)
        if operation is None:
            raise UnknownOperationError(
                f"Operation {request.operation!r} does not exist."
            )
        _check_request(operation, request)
        hashed_holder = holder_key(request.holder_email, self.settings)
        sources = await self._resolve_sources(request, hashed_holder)

        path = operation.build_path(request.params)
        email = normalise_email(request.holder_email)
        limiter = asyncio.Semaphore(self.settings.source_max_concurrent_calls)

        async def call_source(source: Source) -> OperationResult:
            async with limiter:
                try:
                    response = await self.caller.call(
                        source,
                        operation.method,
                        path,
                        json_body=request.body,
                        holder_email=email,
                    )
                except SourceUnavailableError as exc:
                    return OperationResult(
                        source_code=source.code,
                        status_code=502,
                        ok=False,
                        message=exc.message,
                    )
            return _to_result(source, response.status_code, response.body)

        results = await asyncio.gather(*(call_source(s) for s in sources))
        logger.info("Ran %s on %d source(s)", operation.name, len(results))
        return HolderOperationResponse(items=list(results))

    async def _resolve_sources(
        self, request: HolderOperationRequest, hashed_holder: str
    ) -> list[Source]:
        linked_ids = set(
            await self.routing.list_linked_source_ids(hashed_holder)
        )
        if request.source_code is None:
            linked_sources = await self.sources.list_by_ids(linked_ids)
            return [source for source in linked_sources if source.is_active]

        source = await self.sources.get_by_code(request.source_code)
        if source is None:
            raise SourceNotFoundError(
                f"Source {request.source_code} does not exist."
            )
        if not source.is_active:
            raise SourceInactiveError(f"Source {source.code} is inactive.")
        if source.id not in linked_ids:
            raise HolderNotLinkedError(
                f"Source {source.code} has no records for this holder."
            )
        return [source]

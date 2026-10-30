"""Outbound calls from the connector to DCS sources (the API caller).

Every call goes to the source's configured ``base_url`` with the
source's own API key, so a source only ever receives the key it issued.
A source that is one tenant of a shared DCS also gets its ``tenant_id``
as the ``X-Tenant-ID`` header, which is how the DCS picks the tenant
(and its database and API key) for a call without a user token.
Paths are built from fixed templates by the caller's users; nothing in
a client request is used as a raw path or URL.
"""

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import Settings
from app.core.encryption import decrypt_text
from app.features.sources.exceptions import (
    SourceInactiveError,
    SourceUnavailableError,
)
from app.features.sources.models import Source

logger = logging.getLogger(__name__)

HOLDER_EMAIL_HEADER = "X-Holder-Email"
TENANT_ID_HEADER = "X-Tenant-ID"


@dataclass(frozen=True, slots=True)
class SourceResponse:
    """What a source answered: status code and decoded JSON body."""

    status_code: int
    body: Any

    @property
    def is_success(self) -> bool:
        """Return True for a 2xx answer."""
        return 200 <= self.status_code < 300


class SourceCaller:
    """Sends requests to DCS sources and decodes their answers."""

    def __init__(
        self, http_client: httpx.AsyncClient, settings: Settings
    ) -> None:
        self.http_client = http_client
        self.settings = settings

    async def call(
        self,
        source: Source,
        method: str,
        path: str,
        *,
        json_body: Any = None,
        holder_email: str | None = None,
    ) -> SourceResponse:
        """Send one request to ``source`` and return its answer.

        Answers with any HTTP status are returned; only transport
        failures and non-JSON bodies raise.

        Args:
            source: Target DCS instance.
            method: HTTP method.
            path: Path below the source's base URL, starting with "/".
            json_body: Optional JSON request body.
            holder_email: Holder the call is made for, sent as
                ``X-Holder-Email`` so the source can scope it.

        Raises:
            SourceInactiveError: The source has been switched off.
            SourceUnavailableError: The source timed out, could not be
                reached, or did not answer with JSON.
        """
        if not source.is_active:
            raise SourceInactiveError(f"Source {source.code} is inactive.")
        headers = {
            "X-API-Key": decrypt_text(source.encrypted_api_key, self.settings)
        }
        if holder_email is not None:
            headers[HOLDER_EMAIL_HEADER] = holder_email
        if source.tenant_id:
            headers[TENANT_ID_HEADER] = source.tenant_id

        try:
            response = await self.http_client.request(
                method,
                f"{source.base_url}{path}",
                json=json_body,
                headers=headers,
                timeout=self.settings.source_timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            logger.warning("Source %s timed out on %s", source.code, path)
            raise SourceUnavailableError(
                f"Source {source.code} did not answer in time."
            ) from exc
        except httpx.HTTPError as exc:
            logger.warning(
                "Source %s request failed: %s", source.code, type(exc).__name__
            )
            raise SourceUnavailableError(
                f"Source {source.code} could not be reached."
            ) from exc

        try:
            body = response.json()
        except ValueError as exc:
            logger.warning(
                "Source %s answered %s without JSON on %s",
                source.code,
                response.status_code,
                path,
            )
            raise SourceUnavailableError(
                f"Source {source.code} returned an unreadable response."
            ) from exc
        return SourceResponse(status_code=response.status_code, body=body)

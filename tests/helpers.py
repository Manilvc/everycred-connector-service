"""Builders for signed source events used across feature tests."""

import time
import uuid
from typing import Any

from httpx import AsyncClient, Response

from app.core.signatures import (
    DELIVERY_HEADER,
    EVENT_HEADER,
    SIGNATURE_HEADER,
    encode_body,
    sign,
)


def build_event(
    event: str,
    *,
    credential_id: str | None = None,
    request_id: str | None = None,
    holder_email: str | None = "holder@example.com",
    inviter_name: str | None = None,
) -> dict[str, Any]:
    return {
        "id": uuid.uuid4().hex,
        "event": event,
        "created_at": "2026-10-21T10:00:00+00:00",
        "data": {
            "credential_id": credential_id,
            "request_id": request_id,
            "holder_email": holder_email,
            "inviter_name": inviter_name,
        },
    }


async def send_event(
    client: AsyncClient,
    source_code: str,
    secret: str,
    payload: dict[str, Any],
    *,
    delivery_id: str | None = None,
    timestamp: int | None = None,
) -> Response:
    body = encode_body(payload)
    signed_at = int(time.time()) if timestamp is None else timestamp
    return await client.post(
        f"/v1/sources/{source_code}/events",
        content=body,
        headers={
            "Content-Type": "application/json",
            EVENT_HEADER: payload["event"],
            DELIVERY_HEADER: delivery_id or payload["id"],
            SIGNATURE_HEADER: sign(secret, signed_at, body),
        },
    )


def dcs_credential_body(
    *, is_revoked: bool = False, title: str = "B.Tech"
) -> dict[str, Any]:
    """Return a DCS ``GET /v1/user/credential/{uuid}`` style answer."""
    return {
        "status": "success",
        "message": "Credential found",
        "data": {
            "title": title,
            "holder_name": "Test Holder",
            "issuer_name": "Example University",
            "issuer_did": "did:evrc:issuer:example",
            "issuer_email": "",
            "issuer_logo_link": "https://cdn.example.com/logo.png",
            "issuer_description": "",
            "issued_date": "2026-10-01T00:00:00Z",
            "fields": {"grade": "A"},
            "credential_link": "https://cdn.example.com/c.json",
            "credential_image_path": "https://cdn.example.com/c.png",
            "qrcode": "",
            "hash": "abc123",
            "is_revoked": is_revoked,
            "credential_json_content": (
                '{"type": ["VerifiableCredential"], '
                '"validFrom": "2026-10-01T00:00:00Z", '
                '"validUntil": "2030-10-01T00:00:00Z"}'
            ),
            "credential_unique_id": "unique-1",
            "subject_name": "Computer Science",
            "subject_logo_link": "https://cdn.example.com/subject.png",
        },
    }

"""Normalizer for the EveryCRED DCS backend.

The DCS answers ``GET /v1/user/credential/{uuid}`` with its standard
envelope ``{"status", "data", "message"}``; the credential details are
in ``data``, built by the DCS ``VerifierService.view_credentials_service``.
"""

import json
from typing import Any

from app.normalizers.base import (
    CredentialStatus,
    IssuerSummary,
    NormalizationError,
    NormalizedCredential,
    register_normalizer,
)


def _text(details: dict[str, Any], key: str) -> str | None:
    # The DCS fills missing values with "" rather than null; the
    # standard format uses null so clients have one check to make.
    value = details.get(key)
    if value is None or value == "":
        return None
    return str(value)


def _parse_credential_json(raw_json: Any) -> dict[str, Any] | None:
    if isinstance(raw_json, dict):
        return raw_json
    if not isinstance(raw_json, str) or not raw_json:
        return None
    try:
        parsed = json.loads(raw_json)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


@register_normalizer(
    "everycred_dcs", credential_path="/v1/user/credential/{credential_id}"
)
def normalize_everycred_dcs(
    raw_response: dict[str, Any], credential_id: str, source_code: str
) -> NormalizedCredential:
    """Map a DCS credential view response to the standard format.

    Raises:
        NormalizationError: ``data`` is missing or not an object.
    """
    details = raw_response.get("data")
    if not isinstance(details, dict):
        raise NormalizationError("DCS response has no credential data")

    fields = details.get("fields")
    return NormalizedCredential(
        credential_id=credential_id,
        source_code=source_code,
        status=(
            CredentialStatus.REVOKED
            if details.get("is_revoked")
            else CredentialStatus.ISSUED
        ),
        title=_text(details, "title"),
        holder_name=_text(details, "holder_name"),
        issuer=IssuerSummary(
            name=_text(details, "issuer_name"),
            did=_text(details, "issuer_did"),
            email=_text(details, "issuer_email"),
            logo_url=_text(details, "issuer_logo_link"),
            description=_text(details, "issuer_description"),
        ),
        issued_at=_text(details, "issued_date"),
        fields=fields if isinstance(fields, dict) else {},
        credential_url=_text(details, "credential_link"),
        image_url=_text(details, "credential_image_path"),
        qr_code_url=_text(details, "qrcode"),
        hash=_text(details, "hash"),
        credential_json=_parse_credential_json(
            details.get("credential_json_content")
        ),
    )

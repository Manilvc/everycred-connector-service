"""OpenAPI metadata rendered by ReDoc (``/redoc``) and Swagger (``/docs``).

Tag names must match the ``tags`` declared on each feature's router.
"""

from typing import Any

from fastapi import FastAPI

API_DESCRIPTION = """
Connects EveryCRED DCS instances (for example DCS-India and
DCS-Education) to verifier applications and the holder service.

- DCS sources send signed **events** when a credential is issued or
  revoked, or a request is created or updated.
- The connector keeps a **routing table** (credential id to source,
  holder to sources). It never stores credential contents.
- Verifiers and the holder service **look up credentials**; the
  connector calls the right source and returns one standard format.
- The holder service runs **holder operations** (requests, workflows,
  KYC) that the connector forwards to the right source.
- Events are forwarded to the holder service as signed webhooks.

## Authentication

- **Operators** send `X-Admin-Key` to manage sources and clients.
- **Clients** send the `X-API-Key` issued when they were registered.
  Verifier clients may only look up a credential by id.
- **DCS sources** sign events with their webhook secret:
  `X-EveryCRED-Signature: t=<unix time>,v1=<hex HMAC-SHA256 of
  "<t>.<raw body>">`.

## Errors

Every error response has the shape
`{"error": {"code", "message", "request_id"}}`. `code` is stable and
safe to branch on; `request_id` matches the `X-Request-ID` header.
"""

OPENAPI_TAGS: list[dict[str, Any]] = [
    {
        "name": "Health",
        "description": "Liveness and readiness probes. No authentication.",
    },
    {
        "name": "Sources",
        "description": (
            "DCS instances the connector routes to. Registering a source "
            "returns its webhook signing secret once. Operators only."
        ),
    },
    {
        "name": "Clients",
        "description": (
            "Verifier applications and the holder service. A new API key "
            "is returned once; only its hash is stored. Operators only."
        ),
    },
    {
        "name": "Source Events",
        "description": (
            "Signed webhooks from DCS sources. Each delivery id is "
            "applied once; retries are acknowledged as duplicates."
        ),
    },
    {
        "name": "Credentials",
        "description": (
            "Credential lookups in the standard format. Holder lookups "
            "take the email in the body and are for the holder service "
            "only."
        ),
    },
    {
        "name": "Holder Operations",
        "description": (
            "Named operations forwarded to DCS sources for a holder, "
            "such as listing requests or submitting a form. Holder "
            "service only."
        ),
    },
]

LICENSE_INFO = {"name": "MIT", "identifier": "MIT"}


def add_tag_groups(app: FastAPI) -> None:
    """Group tags in the ReDoc sidebar by who calls them."""
    build_schema = app.openapi

    def openapi_with_tag_groups() -> dict[str, Any]:
        if app.openapi_schema is None:
            schema = build_schema()
            schema["x-tagGroups"] = [
                {"name": "Operators", "tags": ["Sources", "Clients"]},
                {"name": "DCS sources", "tags": ["Source Events"]},
                {
                    "name": "Clients",
                    "tags": ["Credentials", "Holder Operations"],
                },
                {"name": "Operations", "tags": ["Health"]},
            ]
            app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = openapi_with_tag_groups  # type: ignore[method-assign]

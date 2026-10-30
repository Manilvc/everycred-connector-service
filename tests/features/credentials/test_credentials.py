import json

import httpx
from httpx import AsyncClient

from tests.conftest import FakeSources, register_client, register_source
from tests.helpers import build_event, dcs_credential_body, send_event


async def _issue(
    client: AsyncClient,
    secret: str,
    credential_id: str,
    holder_email: str = "holder@example.com",
    source_code: str = "dcs-india",
) -> None:
    response = await send_event(
        client,
        source_code,
        secret,
        build_event(
            "credential.issued",
            credential_id=credential_id,
            holder_email=holder_email,
        ),
    )
    assert response.status_code == 202


async def test_verifier_gets_normalized_credential_from_its_source(
    client: AsyncClient, fake_sources: FakeSources
) -> None:
    secret = await register_source(client)
    await _issue(client, secret, "cred-1")
    headers = await register_client(client, "verifier")
    fake_sources.handle(
        "dcs-india.example.com",
        lambda request: httpx.Response(200, json=dcs_credential_body()),
    )

    response = await client.get("/v1/credentials/cred-1", headers=headers)

    body = response.json()
    assert response.status_code == 200
    assert body["source_code"] == "dcs-india"
    assert body["status"] == "issued"
    assert body["title"] == "B.Tech"
    assert body["issuer"]["email"] is None
    assert body["qr_code_url"] is None
    assert body["credential_json"]["type"] == ["VerifiableCredential"]
    assert body["valid_until"] == "2030-10-01T00:00:00Z"
    source_request = fake_sources.requests[0]
    assert source_request.url.path == "/v1/user/credential/cred-1"
    assert source_request.headers["X-API-Key"] == "dcs-india-source-api-key"


async def test_unrouted_credential_is_not_found(client: AsyncClient) -> None:
    headers = await register_client(client, "verifier")

    response = await client.get("/v1/credentials/unknown", headers=headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "credential_not_found"


async def test_source_404_is_reported_as_not_found(
    client: AsyncClient, fake_sources: FakeSources
) -> None:
    secret = await register_source(client)
    await _issue(client, secret, "cred-1")
    headers = await register_client(client, "verifier")
    fake_sources.handle(
        "dcs-india.example.com",
        lambda request: httpx.Response(404, json={"status": "fail"}),
    )

    response = await client.get("/v1/credentials/cred-1", headers=headers)

    assert response.status_code == 404


async def test_source_failure_is_a_bad_gateway(
    client: AsyncClient, fake_sources: FakeSources
) -> None:
    secret = await register_source(client)
    await _issue(client, secret, "cred-1")
    headers = await register_client(client, "verifier")
    fake_sources.handle(
        "dcs-india.example.com",
        lambda request: httpx.Response(500, text="boom"),
    )

    response = await client.get("/v1/credentials/cred-1", headers=headers)

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "source_unavailable"


async def test_holder_lookup_collects_from_every_source(
    client: AsyncClient, fake_sources: FakeSources
) -> None:
    india_secret = await register_source(client, "dcs-india")
    edu_secret = await register_source(client, "dcs-edu")
    await _issue(client, india_secret, "cred-india")
    await _issue(client, edu_secret, "cred-edu", source_code="dcs-edu")
    await _issue(client, india_secret, "cred-other", "other@example.com")
    headers = await register_client(client, "holder_service")
    fake_sources.handle(
        "dcs-india.example.com",
        lambda request: httpx.Response(200, json=dcs_credential_body()),
    )
    # dcs-edu has no handler, so it is unreachable.

    response = await client.post(
        "/v1/holders/credentials/lookup",
        json={"holder_email": "HOLDER@example.com"},
        headers=headers,
    )

    items = {item["credential_id"]: item for item in response.json()["items"]}
    assert response.status_code == 200
    assert set(items) == {"cred-india", "cred-edu"}
    assert items["cred-india"]["credential"]["title"] == "B.Tech"
    assert items["cred-india"]["first_seen_at"]
    assert items["cred-india"]["status_changed_at"]
    assert items["cred-edu"]["credential"] is None
    assert items["cred-edu"]["error"]


async def test_holder_cannot_get_another_holders_credential(
    client: AsyncClient, fake_sources: FakeSources
) -> None:
    secret = await register_source(client)
    await _issue(client, secret, "cred-1", "owner@example.com")
    headers = await register_client(client, "holder_service")
    fake_sources.handle(
        "dcs-india.example.com",
        lambda request: httpx.Response(200, json=dcs_credential_body()),
    )

    response = await client.post(
        "/v1/holders/credentials/get",
        json={
            "holder_email": "someone@example.com",
            "credential_id": "cred-1",
        },
        headers=headers,
    )

    assert response.status_code == 404
    assert fake_sources.requests == []


async def test_holder_gets_own_credential(
    client: AsyncClient, fake_sources: FakeSources
) -> None:
    secret = await register_source(client)
    await _issue(client, secret, "cred-1")
    headers = await register_client(client, "holder_service")
    fake_sources.handle(
        "dcs-india.example.com",
        lambda request: httpx.Response(
            200, json=dcs_credential_body(is_revoked=True)
        ),
    )

    response = await client.post(
        "/v1/holders/credentials/get",
        json={"holder_email": "holder@example.com", "credential_id": "cred-1"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "revoked"


async def test_verification_record_is_forwarded_to_the_source(
    client: AsyncClient, fake_sources: FakeSources
) -> None:
    secret = await register_source(client)
    await _issue(client, secret, "unique-1")
    headers = await register_client(client, "holder_service")
    fake_sources.handle(
        "dcs-india.example.com",
        lambda request: httpx.Response(
            201,
            json={
                "status": "success",
                "data": {"id": 7},
                "message": "Information stored successfully",
            },
        ),
    )

    response = await client.post(
        "/v1/credentials/unique-1/verification-analytics",
        json={"verification_status": True, "stage": None, "reason": None},
        headers=headers,
    )

    body = response.json()
    assert response.status_code == 200
    assert body["status_code"] == 201
    assert body["ok"] is True
    assert body["data"] == {"id": 7}
    assert body["message"] == "Information stored successfully"
    source_request = fake_sources.requests[0]
    assert source_request.method == "POST"
    assert source_request.url.path == "/v1/credential/verification/analytics"
    assert source_request.url.params["uuid"] == "unique-1"
    assert json.loads(source_request.content)["verification_status"] is True


async def test_verification_record_for_unknown_credential_is_404(
    client: AsyncClient,
) -> None:
    headers = await register_client(client, "verifier")

    response = await client.post(
        "/v1/credentials/unknown/verification-analytics",
        json={"verification_status": False},
        headers=headers,
    )

    assert response.status_code == 404

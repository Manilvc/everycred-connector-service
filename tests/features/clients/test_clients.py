from httpx import AsyncClient

from tests.conftest import ADMIN_HEADERS, register_client


async def test_create_client_returns_key_once(client: AsyncClient) -> None:
    response = await client.post(
        "/v1/clients",
        json={"name": "Verifier", "kind": "verifier"},
        headers=ADMIN_HEADERS,
    )

    body = response.json()
    assert response.status_code == 201
    assert body["api_key"].startswith(f"ecc_{body['key_prefix']}_")

    listing = await client.get("/v1/clients", headers=ADMIN_HEADERS)
    assert "api_key" not in listing.json()["items"][0]


async def test_unknown_api_key_is_rejected(client: AsyncClient) -> None:
    response = await client.get(
        "/v1/credentials/abc",
        headers={"X-API-Key": "ecc_000000000000_not-a-real-key"},
    )

    assert response.status_code == 401


async def test_revoked_client_cannot_call_the_api(
    client: AsyncClient,
) -> None:
    created = await client.post(
        "/v1/clients",
        json={"name": "Verifier", "kind": "verifier"},
        headers=ADMIN_HEADERS,
    )
    headers = {"X-API-Key": created.json()["api_key"]}

    revoke = await client.post(
        f"/v1/clients/{created.json()['id']}/revoke", headers=ADMIN_HEADERS
    )
    response = await client.get("/v1/credentials/abc", headers=headers)

    assert revoke.json()["revoked_at"] is not None
    assert response.status_code == 401


async def test_verifier_cannot_use_holder_endpoints(
    client: AsyncClient,
) -> None:
    headers = await register_client(client, "verifier")

    response = await client.post(
        "/v1/holders/credentials/lookup",
        json={"holder_email": "holder@example.com"},
        headers=headers,
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"

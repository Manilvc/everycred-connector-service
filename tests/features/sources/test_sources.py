from httpx import AsyncClient

from tests.conftest import ADMIN_HEADERS, register_source


async def test_create_source_requires_admin_key(client: AsyncClient) -> None:
    response = await client.post(
        "/v1/sources",
        json={
            "code": "dcs-india",
            "name": "DCS India",
            "base_url": "https://dcs-india.example.com",
            "api_key": "dcs-india-source-api-key",
        },
        headers={"X-Admin-Key": "wrong"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_failed"


async def test_create_source_returns_secret_once_and_hides_api_key(
    client: AsyncClient,
) -> None:
    secret = await register_source(client)

    assert secret.startswith("whsec_")
    response = await client.get("/v1/sources/dcs-india", headers=ADMIN_HEADERS)
    body = response.json()
    assert response.status_code == 200
    assert "webhook_secret" not in body
    assert "api_key" not in body
    assert body["base_url"] == "https://dcs-india.example.com"


async def test_create_source_rejects_duplicate_code(
    client: AsyncClient,
) -> None:
    await register_source(client)

    response = await client.post(
        "/v1/sources",
        json={
            "code": "dcs-india",
            "name": "Again",
            "base_url": "https://other.example.com",
            "api_key": "another-source-api-key",
        },
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "source_code_taken"


async def test_create_source_rejects_unknown_normalizer(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/v1/sources",
        json={
            "code": "dcs-edu",
            "name": "DCS Education",
            "base_url": "https://dcs-edu.example.com",
            "api_key": "dcs-edu-source-api-key",
            "normalizer": "nope",
        },
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unknown_normalizer"


async def test_create_source_rejects_url_with_credentials(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/v1/sources",
        json={
            "code": "dcs-edu",
            "name": "DCS Education",
            "base_url": "https://user:pass@dcs-edu.example.com",
            "api_key": "dcs-edu-source-api-key",
        },
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 422


async def test_update_source_deactivates_it(client: AsyncClient) -> None:
    await register_source(client)

    response = await client.patch(
        "/v1/sources/dcs-india",
        json={"is_active": False, "name": "DCS India (old)"},
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["is_active"] is False
    assert response.json()["name"] == "DCS India (old)"


async def test_rotate_webhook_secret_returns_a_new_secret(
    client: AsyncClient,
) -> None:
    old_secret = await register_source(client)

    response = await client.post(
        "/v1/sources/dcs-india/webhook-secret", headers=ADMIN_HEADERS
    )

    assert response.status_code == 200
    assert response.json()["webhook_secret"] != old_secret


async def test_list_sources_is_paginated(client: AsyncClient) -> None:
    await register_source(client, "dcs-india")
    await register_source(client, "dcs-edu")

    response = await client.get(
        "/v1/sources", params={"limit": 1}, headers=ADMIN_HEADERS
    )

    body = response.json()
    assert body["total"] == 2
    assert [item["code"] for item in body["items"]] == ["dcs-edu"]


async def test_tenant_origin_is_stored_without_a_trailing_slash(
    client: AsyncClient,
) -> None:
    await register_source(client)

    response = await client.patch(
        "/v1/sources/dcs-india",
        json={"tenant_origin": "https://tenant-a.example.com/"},
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["tenant_origin"] == "https://tenant-a.example.com"


async def test_tenant_origin_with_a_path_is_rejected(
    client: AsyncClient,
) -> None:
    await register_source(client)

    response = await client.patch(
        "/v1/sources/dcs-india",
        json={"tenant_origin": "https://tenant-a.example.com/login"},
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 422


async def test_update_keeps_tenant_origin_unless_sent(
    client: AsyncClient,
) -> None:
    await register_source(client)
    await client.patch(
        "/v1/sources/dcs-india",
        json={"tenant_origin": "https://tenant-a.example.com"},
        headers=ADMIN_HEADERS,
    )

    kept = await client.patch(
        "/v1/sources/dcs-india",
        json={"name": "Renamed"},
        headers=ADMIN_HEADERS,
    )
    cleared = await client.patch(
        "/v1/sources/dcs-india",
        json={"tenant_origin": None},
        headers=ADMIN_HEADERS,
    )

    assert kept.json()["tenant_origin"] == "https://tenant-a.example.com"
    assert cleared.json()["tenant_origin"] is None

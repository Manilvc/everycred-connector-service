import json

import httpx
import pytest
from httpx import AsyncClient

from tests.conftest import FakeSources, register_client, register_source
from tests.helpers import build_event, send_event


@pytest.fixture
async def holder_headers(client: AsyncClient) -> dict[str, str]:
    return await register_client(client, "holder_service")


async def _link_holder(
    client: AsyncClient, source_code: str, holder_email: str
) -> None:
    secret = await register_source(client, source_code)
    response = await send_event(
        client,
        source_code,
        secret,
        build_event(
            "request.created", request_id="req-1", holder_email=holder_email
        ),
    )
    assert response.status_code == 202


def _dcs_ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "status": "success",
            "data": {"path": request.url.raw_path.decode()},
            "message": "OK",
        },
    )


async def test_item_operation_calls_the_named_source(
    client: AsyncClient,
    fake_sources: FakeSources,
    holder_headers: dict[str, str],
) -> None:
    await _link_holder(client, "dcs-india", "holder@example.com")
    fake_sources.handle("dcs-india.example.com", _dcs_ok)

    response = await client.post(
        "/v1/holders/operations",
        json={
            "holder_email": "Holder@Example.com",
            "operation": "workflow.node_submit",
            "source_code": "dcs-india",
            "params": {"request_uuid": "r-1", "node_key": "kyc:step"},
            "body": {"answers": {"name": "Test"}},
        },
        headers=holder_headers,
    )

    assert response.status_code == 200
    [item] = response.json()["items"]
    assert item["ok"] is True
    assert item["message"] == "OK"
    assert item["data"]["path"] == (
        "/v1/internal/holder/workflow-requests/r-1/nodes/kyc%3Astep/submit"
    )
    source_request = fake_sources.requests[0]
    assert source_request.method == "POST"
    assert source_request.headers["X-Holder-Email"] == "holder@example.com"
    assert json.loads(source_request.content) == {"answers": {"name": "Test"}}


async def test_list_operation_fans_out_to_linked_sources(
    client: AsyncClient,
    fake_sources: FakeSources,
    holder_headers: dict[str, str],
) -> None:
    await _link_holder(client, "dcs-india", "holder@example.com")
    await _link_holder(client, "dcs-edu", "holder@example.com")
    await _link_holder(client, "dcs-other", "other@example.com")
    fake_sources.handle("dcs-india.example.com", _dcs_ok)
    # dcs-edu is unreachable and must not fail the whole call.

    response = await client.post(
        "/v1/holders/operations",
        json={
            "holder_email": "holder@example.com",
            "operation": "requests.list",
        },
        headers=holder_headers,
    )

    items = {item["source_code"]: item for item in response.json()["items"]}
    assert set(items) == {"dcs-india", "dcs-edu"}
    assert items["dcs-india"]["ok"] is True
    assert items["dcs-edu"]["ok"] is False
    assert items["dcs-edu"]["status_code"] == 502


async def test_find_operation_looks_up_a_request_in_every_source(
    client: AsyncClient,
    fake_sources: FakeSources,
    holder_headers: dict[str, str],
) -> None:
    await _link_holder(client, "dcs-india", "holder@example.com")
    await _link_holder(client, "dcs-edu", "holder@example.com")
    fake_sources.handle("dcs-india.example.com", _dcs_ok)
    fake_sources.handle("dcs-edu.example.com", _dcs_ok)

    response = await client.post(
        "/v1/holders/operations",
        json={
            "holder_email": "holder@example.com",
            "operation": "requests.find",
            "params": {"request_id": "req-1"},
        },
        headers=holder_headers,
    )

    assert response.status_code == 200
    paths = {item["data"]["path"] for item in response.json()["items"]}
    assert paths == {"/v1/internal/holder/requests/req-1"}
    assert len(fake_sources.requests) == 2


async def test_registered_operation_puts_to_every_linked_source(
    client: AsyncClient,
    fake_sources: FakeSources,
    holder_headers: dict[str, str],
) -> None:
    await _link_holder(client, "dcs-india", "holder@example.com")
    await _link_holder(client, "dcs-edu", "holder@example.com")
    fake_sources.handle("dcs-india.example.com", _dcs_ok)
    fake_sources.handle("dcs-edu.example.com", _dcs_ok)

    response = await client.post(
        "/v1/holders/operations",
        json={
            "holder_email": "holder@example.com",
            "operation": "holder.registered",
        },
        headers=holder_headers,
    )

    assert response.status_code == 200
    assert {item["source_code"] for item in response.json()["items"]} == {
        "dcs-india",
        "dcs-edu",
    }
    assert {request.method for request in fake_sources.requests} == {"PUT"}
    assert {request.url.path for request in fake_sources.requests} == {
        "/v1/internal/holder/registered"
    }


async def test_profile_operation_puts_the_body_to_every_linked_source(
    client: AsyncClient,
    fake_sources: FakeSources,
    holder_headers: dict[str, str],
) -> None:
    await _link_holder(client, "dcs-india", "holder@example.com")
    await _link_holder(client, "dcs-edu", "holder@example.com")
    fake_sources.handle("dcs-india.example.com", _dcs_ok)
    fake_sources.handle("dcs-edu.example.com", _dcs_ok)
    profile = {"name": "Asha Rao", "mobile": "+919876543210"}

    response = await client.post(
        "/v1/holders/operations",
        json={
            "holder_email": "holder@example.com",
            "operation": "holder.profile_updated",
            "body": profile,
        },
        headers=holder_headers,
    )

    assert response.status_code == 200
    assert len(response.json()["items"]) == 2
    assert {request.method for request in fake_sources.requests} == {"PUT"}
    assert {request.url.path for request in fake_sources.requests} == {
        "/v1/internal/holder/profile"
    }
    assert all(
        json.loads(request.content) == profile
        for request in fake_sources.requests
    )


@pytest.mark.parametrize(
    ("payload", "error_code"),
    [
        ({"operation": "files.delete"}, "unknown_operation"),
        (
            {"operation": "requests.get", "source_code": "dcs-india"},
            "invalid_params",
        ),
        (
            {"operation": "requests.get", "params": {"request_id": "r"}},
            "source_required",
        ),
        (
            {
                "operation": "requests.get",
                "source_code": "dcs-india",
                "params": {"request_id": "r"},
                "body": {"x": 1},
            },
            "invalid_params",
        ),
    ],
)
async def test_invalid_operation_requests_are_rejected(
    client: AsyncClient,
    holder_headers: dict[str, str],
    payload: dict[str, object],
    error_code: str,
) -> None:
    response = await client.post(
        "/v1/holders/operations",
        json={"holder_email": "holder@example.com", **payload},
        headers=holder_headers,
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == error_code


async def test_path_traversal_in_params_is_rejected(
    client: AsyncClient, holder_headers: dict[str, str]
) -> None:
    response = await client.post(
        "/v1/holders/operations",
        json={
            "holder_email": "holder@example.com",
            "operation": "requests.get",
            "source_code": "dcs-india",
            "params": {"request_id": "../../admin"},
        },
        headers=holder_headers,
    )

    assert response.status_code == 422


async def test_source_without_holder_records_is_refused(
    client: AsyncClient,
    fake_sources: FakeSources,
    holder_headers: dict[str, str],
) -> None:
    await _link_holder(client, "dcs-india", "other@example.com")

    response = await client.post(
        "/v1/holders/operations",
        json={
            "holder_email": "holder@example.com",
            "operation": "kyc.detail",
            "source_code": "dcs-india",
        },
        headers=holder_headers,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "holder_not_linked"
    assert fake_sources.requests == []

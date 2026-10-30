import json
import time

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.encryption import decrypt_text
from app.features.notifications.models import HolderNotification
from app.features.routing.models import CredentialRoute, HolderLink
from tests.conftest import register_source
from tests.helpers import build_event, send_event


async def test_issued_event_creates_route_link_and_notification(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    secret = await register_source(client)
    payload = build_event(
        "credential.issued",
        credential_id="cred-1",
        holder_email="Holder@Example.com",
    )

    response = await send_event(client, "dcs-india", secret, payload)

    assert response.status_code == 202
    assert response.json() == {"accepted": True, "duplicate": False}
    async with session_factory() as session:
        route = await session.scalar(select(CredentialRoute))
        link = await session.scalar(select(HolderLink))
        notification = await session.scalar(select(HolderNotification))
    assert route is not None
    assert route.credential_id == "cred-1"
    assert route.status == "issued"
    assert link is not None
    assert link.holder_key == route.holder_key
    # The email is never stored in clear text.
    assert "holder@example.com" not in (route.holder_key or "")
    assert notification is not None
    assert notification.encrypted_payload is not None
    forwarded = json.loads(
        decrypt_text(notification.encrypted_payload, get_settings())
    )
    assert forwarded["event"] == "credential.issued"
    assert forwarded["data"]["holder_email"] == "holder@example.com"
    assert forwarded["data"]["source_code"] == "dcs-india"


async def test_revoked_event_updates_the_route_status(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    secret = await register_source(client)
    await send_event(
        client,
        "dcs-india",
        secret,
        build_event("credential.issued", credential_id="cred-1"),
    )

    await send_event(
        client,
        "dcs-india",
        secret,
        build_event("credential.revoked", credential_id="cred-1"),
    )

    async with session_factory() as session:
        routes = list(await session.scalars(select(CredentialRoute)))
    assert [route.status for route in routes] == ["revoked"]


async def test_wrong_signature_is_rejected(client: AsyncClient) -> None:
    await register_source(client)

    response = await send_event(
        client,
        "dcs-india",
        "whsec_not-the-secret",
        build_event("credential.issued", credential_id="cred-1"),
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_signature"


async def test_stale_signature_is_rejected(client: AsyncClient) -> None:
    secret = await register_source(client)

    response = await send_event(
        client,
        "dcs-india",
        secret,
        build_event("credential.issued", credential_id="cred-1"),
        timestamp=int(time.time()) - 3600,
    )

    assert response.status_code == 401


async def test_repeated_delivery_is_applied_once(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    secret = await register_source(client)
    payload = build_event("credential.issued", credential_id="cred-1")

    first = await send_event(client, "dcs-india", secret, payload)
    second = await send_event(client, "dcs-india", secret, payload)

    assert first.json()["duplicate"] is False
    assert second.json()["duplicate"] is True
    async with session_factory() as session:
        notifications = list(await session.scalars(select(HolderNotification)))
    assert len(notifications) == 1


async def test_credential_owned_by_another_source_is_a_conflict(
    client: AsyncClient,
) -> None:
    india_secret = await register_source(client, "dcs-india")
    edu_secret = await register_source(client, "dcs-edu")
    await send_event(
        client,
        "dcs-india",
        india_secret,
        build_event("credential.issued", credential_id="cred-1"),
    )

    response = await send_event(
        client,
        "dcs-edu",
        edu_secret,
        build_event("credential.issued", credential_id="cred-1"),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "credential_source_conflict"


async def test_credential_event_without_credential_id_is_invalid(
    client: AsyncClient,
) -> None:
    secret = await register_source(client)

    response = await send_event(
        client, "dcs-india", secret, build_event("credential.issued")
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_event"


async def test_request_event_links_holder_without_a_route(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    secret = await register_source(client)

    response = await send_event(
        client,
        "dcs-india",
        secret,
        build_event("request.created", request_id="req-1"),
    )

    assert response.status_code == 202
    async with session_factory() as session:
        assert await session.scalar(select(CredentialRoute)) is None
        assert await session.scalar(select(HolderLink)) is not None


async def test_holder_invited_links_holder_and_forwards_inviter(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    secret = await register_source(client)

    response = await send_event(
        client,
        "dcs-india",
        secret,
        build_event("holder.invited", inviter_name="Example University"),
    )

    assert response.status_code == 202
    async with session_factory() as session:
        assert await session.scalar(select(CredentialRoute)) is None
        assert await session.scalar(select(HolderLink)) is not None
        notification = await session.scalar(select(HolderNotification))
    assert notification is not None
    assert notification.encrypted_payload is not None
    forwarded = json.loads(
        decrypt_text(notification.encrypted_payload, get_settings())
    )
    assert forwarded["event"] == "holder.invited"
    assert forwarded["data"]["inviter_name"] == "Example University"
    assert forwarded["data"]["holder_email"] == "holder@example.com"


async def test_holder_invited_without_holder_email_is_invalid(
    client: AsyncClient,
) -> None:
    secret = await register_source(client)

    response = await send_event(
        client,
        "dcs-india",
        secret,
        build_event("holder.invited", holder_email=None),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_event"


async def test_unknown_source_is_not_found(client: AsyncClient) -> None:
    response = await send_event(
        client,
        "dcs-missing",
        "whsec_x",
        build_event("credential.issued", credential_id="cred-1"),
    )

    assert response.status_code == 404

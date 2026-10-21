import httpx
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.signatures import SIGNATURE_HEADER, is_signature_valid
from app.features.notifications.models import (
    HolderNotification,
    NotificationStatus,
)
from app.worker import run_once
from tests.conftest import FakeSources, register_source
from tests.helpers import build_event, send_event

HOLDER_HOST = "holder.example.com"


async def _queue_one(client: AsyncClient) -> None:
    secret = await register_source(client)
    await send_event(
        client,
        "dcs-india",
        secret,
        build_event("credential.issued", credential_id="cred-1"),
    )


async def _only_notification(
    session_factory: async_sessionmaker[AsyncSession],
) -> HolderNotification:
    async with session_factory() as session:
        notification = await session.scalar(select(HolderNotification))
    assert notification is not None
    return notification


async def test_worker_delivers_a_signed_event_and_clears_the_payload(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    outbound_client: httpx.AsyncClient,
    fake_sources: FakeSources,
) -> None:
    await _queue_one(client)
    fake_sources.handle(HOLDER_HOST, lambda request: httpx.Response(202))
    settings = get_settings()

    delivered = await run_once(session_factory, outbound_client, settings)

    assert delivered == 1
    [holder_request] = fake_sources.requests
    secret = settings.holder_service_webhook_secret
    assert secret is not None
    assert is_signature_valid(
        secret.get_secret_value(),
        holder_request.headers[SIGNATURE_HEADER],
        holder_request.content,
        tolerance_seconds=60,
    )
    notification = await _only_notification(session_factory)
    assert notification.status is NotificationStatus.DELIVERED
    assert notification.encrypted_payload is None


async def test_server_error_is_retried_later(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    outbound_client: httpx.AsyncClient,
    fake_sources: FakeSources,
) -> None:
    await _queue_one(client)
    fake_sources.handle(HOLDER_HOST, lambda request: httpx.Response(503))

    delivered = await run_once(
        session_factory, outbound_client, get_settings()
    )

    notification = await _only_notification(session_factory)
    assert delivered == 0
    assert notification.status is NotificationStatus.PENDING
    assert notification.attempts == 1
    assert notification.encrypted_payload is not None
    # Not due again until the backoff has passed.
    assert (
        await run_once(session_factory, outbound_client, get_settings()) == 0
    )
    assert len(fake_sources.requests) == 1


async def test_unreadable_row_fails_without_blocking_others(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    outbound_client: httpx.AsyncClient,
    fake_sources: FakeSources,
) -> None:
    async with session_factory() as session:
        session.add(
            HolderNotification(
                event="credential.issued", encrypted_payload="not-fernet"
            )
        )
        await session.commit()
    await _queue_one(client)
    fake_sources.handle(HOLDER_HOST, lambda request: httpx.Response(202))

    delivered = await run_once(
        session_factory, outbound_client, get_settings()
    )

    async with session_factory() as session:
        statuses = sorted(
            notification.status
            for notification in await session.scalars(
                select(HolderNotification)
            )
        )
    assert delivered == 1
    assert statuses == [
        NotificationStatus.DELIVERED,
        NotificationStatus.FAILED,
    ]


async def test_client_error_fails_without_retry(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    outbound_client: httpx.AsyncClient,
    fake_sources: FakeSources,
) -> None:
    await _queue_one(client)
    fake_sources.handle(HOLDER_HOST, lambda request: httpx.Response(400))

    await run_once(session_factory, outbound_client, get_settings())

    notification = await _only_notification(session_factory)
    assert notification.status is NotificationStatus.FAILED
    assert notification.encrypted_payload is None

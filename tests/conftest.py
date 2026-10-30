"""Shared pytest fixtures."""

import os
from collections.abc import AsyncIterator, Callable
from typing import Any

# Settings are read when app.main is imported, so the environment must
# be prepared first. Values are assigned (not defaulted) so a developer's
# .env file cannot change test behaviour. The MySQL URL is never
# connected to: the session dependency is replaced with SQLite below.
os.environ["DATABASE_URL"] = "mysql+aiomysql://test:test@127.0.0.1:3306/test"
os.environ["ADMIN_API_KEY"] = "test-admin-key-" + "a" * 32
os.environ["API_KEY_HASH_SECRET"] = "test-api-key-secret-" + "b" * 32
os.environ["HOLDER_KEY_SECRET"] = "test-holder-key-secret-" + "c" * 32
# A fixed, publicly known Fernet key: fine for tests, never for real data.
os.environ["DATA_ENCRYPTION_KEYS"] = (
    "Y29ubmVjdG9yLXNlcnZpY2UtdGVzdC1rZXktMzJieXQ="
)
os.environ["HOLDER_SERVICE_WEBHOOK_URL"] = "https://holder.example.com/v1/x"
os.environ["HOLDER_SERVICE_WEBHOOK_SECRET"] = "test-holder-webhook-" + "d" * 32
os.environ["LOG_JSON"] = "false"
os.environ["ENVIRONMENT"] = "local"

import httpx  # noqa: E402
import pytest  # noqa: E402
from asgi_lifespan import LifespanManager  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import event  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool  # noqa: E402

# Model modules are imported so Base.metadata knows every table.
import app.features.clients.models  # noqa: E402, F401
import app.features.events.models  # noqa: E402, F401
import app.features.notifications.models  # noqa: E402, F401
import app.features.routing.models  # noqa: E402, F401
import app.features.sources.models  # noqa: E402, F401
from app.core.database import Base, get_db_session  # noqa: E402
from app.core.http_client import get_http_client  # noqa: E402
from app.main import create_app  # noqa: E402

ADMIN_HEADERS = {"X-Admin-Key": os.environ["ADMIN_API_KEY"]}

SourceHandler = Callable[[httpx.Request], httpx.Response]


class FakeSources:
    """Routes outbound source calls to per-test handlers.

    Tests register a handler per base URL host; every request made is
    recorded so assertions can inspect paths and headers.
    """

    def __init__(self) -> None:
        self.handlers: dict[str, SourceHandler] = {}
        self.requests: list[httpx.Request] = []

    def handle(self, host: str, handler: SourceHandler) -> None:
        self.handlers[host] = handler

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        handler = self.handlers.get(request.url.host)
        if handler is None:
            raise httpx.ConnectError("no fake for host", request=request)
        return handler(request)


def _enforce_foreign_keys(
    dbapi_connection: Any, connection_record: Any
) -> None:
    # SQLite ignores foreign keys unless asked. MySQL always enforces
    # them, so tests must too, or rows inserted in the wrong order pass
    # here and fail in production.
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    # StaticPool keeps one connection open, so every session sees the
    # same in-memory database for the duration of the test.
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    event.listen(engine.sync_engine, "connect", _enforce_foreign_keys)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
def fake_sources() -> FakeSources:
    return FakeSources()


@pytest.fixture
async def outbound_client(
    fake_sources: FakeSources,
) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(fake_sources)
    ) as http_client:
        yield http_client


@pytest.fixture
def app(
    session_factory: async_sessionmaker[AsyncSession],
    outbound_client: httpx.AsyncClient,
) -> FastAPI:
    application = create_app()

    async def get_test_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    application.dependency_overrides[get_db_session] = get_test_db_session
    application.dependency_overrides[get_http_client] = lambda: outbound_client
    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with LifespanManager(app) as manager:
        transport = ASGITransport(app=manager.app)
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as http_client:
            yield http_client


async def register_source(client: AsyncClient, code: str = "dcs-india") -> str:
    """Register a source at https://<code>.example.com; return its secret."""
    response = await client.post(
        "/v1/sources",
        json={
            "code": code,
            "name": code.upper(),
            "base_url": f"https://{code}.example.com",
            "api_key": f"{code}-source-api-key",
        },
        headers=ADMIN_HEADERS,
    )
    assert response.status_code == 201, response.text
    return response.json()["webhook_secret"]


async def register_client(client: AsyncClient, kind: str) -> dict[str, str]:
    """Register a client of ``kind`` and return its auth headers."""
    response = await client.post(
        "/v1/clients",
        json={"name": f"{kind} app", "kind": kind},
        headers=ADMIN_HEADERS,
    )
    assert response.status_code == 201, response.text
    return {"X-API-Key": response.json()["api_key"]}

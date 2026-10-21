"""Dependency providers for the sources feature."""

from typing import Annotated

from fastapi import Depends

from app.core.config import SettingsDep
from app.core.database import DbSession
from app.core.http_client import HttpClient
from app.features.sources.caller import SourceCaller
from app.features.sources.service import SourceService


def get_source_service(
    session: DbSession, settings: SettingsDep
) -> SourceService:
    """Build a source service bound to the request's session."""
    return SourceService(session, settings)


def get_source_caller(
    http_client: HttpClient, settings: SettingsDep
) -> SourceCaller:
    """Build a caller that uses the shared HTTP client."""
    return SourceCaller(http_client, settings)


SourceServiceDep = Annotated[SourceService, Depends(get_source_service)]
SourceCallerDep = Annotated[SourceCaller, Depends(get_source_caller)]

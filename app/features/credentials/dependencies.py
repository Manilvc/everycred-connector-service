"""Dependency providers for the credentials feature."""

from typing import Annotated

from fastapi import Depends

from app.core.config import SettingsDep
from app.core.database import DbSession
from app.features.credentials.service import CredentialService
from app.features.sources.dependencies import SourceCallerDep


def get_credential_service(
    session: DbSession, caller: SourceCallerDep, settings: SettingsDep
) -> CredentialService:
    """Build a credential service for one request."""
    return CredentialService(session, caller, settings)


CredentialServiceDep = Annotated[
    CredentialService, Depends(get_credential_service)
]

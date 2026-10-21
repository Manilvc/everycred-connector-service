"""Dependency providers for the operations feature."""

from typing import Annotated

from fastapi import Depends

from app.core.config import SettingsDep
from app.core.database import DbSession
from app.features.operations.service import OperationService
from app.features.sources.dependencies import SourceCallerDep


def get_operation_service(
    session: DbSession, caller: SourceCallerDep, settings: SettingsDep
) -> OperationService:
    """Build an operation service for one request."""
    return OperationService(session, caller, settings)


OperationServiceDep = Annotated[
    OperationService, Depends(get_operation_service)
]

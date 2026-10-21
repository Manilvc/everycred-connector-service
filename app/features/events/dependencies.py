"""Dependency providers for the events feature."""

from typing import Annotated

from fastapi import Depends

from app.core.config import SettingsDep
from app.core.database import DbSession
from app.core.http_client import HttpClient
from app.features.events.service import EventService
from app.features.notifications.service import NotificationService
from app.features.sources.service import SourceService


def get_event_service(
    session: DbSession, settings: SettingsDep, http_client: HttpClient
) -> EventService:
    """Build an event service whose collaborators share one session."""
    return EventService(
        session,
        settings,
        SourceService(session, settings),
        NotificationService(session, http_client, settings),
    )


EventServiceDep = Annotated[EventService, Depends(get_event_service)]

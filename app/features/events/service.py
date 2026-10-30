"""Processing of webhooks received from DCS sources (the webhook receiver).

For each verified delivery the service, in one transaction:

1. records the delivery id, so a retried delivery is applied once;
2. updates the routing table (credential -> source, holder -> source);
3. queues a notification for the holder service.

``holder.invited`` routes no credential: it only links the holder to the
source, so the holder service can show the invite and later report the
holder's registration back to that source.
"""

import logging

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.signatures import is_signature_valid
from app.features.events.exceptions import (
    CredentialSourceConflictError,
    InvalidEventError,
    InvalidSignatureError,
)
from app.features.events.models import SourceEvent
from app.features.events.repository import SourceEventRepository
from app.features.events.schemas import (
    EventReceipt,
    EventType,
    SourceEventPayload,
)
from app.features.notifications.service import NotificationService
from app.features.routing.holder_keys import holder_key, normalise_email
from app.features.routing.repository import RoutingRepository
from app.features.sources.exceptions import SourceInactiveError
from app.features.sources.models import Source
from app.features.sources.service import SourceService

logger = logging.getLogger(__name__)

_CREDENTIAL_STATUS_BY_EVENT = {
    EventType.CREDENTIAL_ISSUED: "issued",
    EventType.CREDENTIAL_REVOKED: "revoked",
}


class EventService:
    """Verifies and applies webhooks from DCS sources.

    Attributes:
        session: Unit of work the service commits.
        settings: Signature tolerance and holder key secret.
        sources: Looks up the sending source and its secret.
        events: Persistence for received deliveries.
        routing: Persistence for the routing table.
        notifications: Outbox for the holder service.
    """

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        source_service: SourceService,
        notification_service: NotificationService,
    ) -> None:
        self.session = session
        self.settings = settings
        self.sources = source_service
        self.events = SourceEventRepository(session)
        self.routing = RoutingRepository(session)
        self.notifications = notification_service

    async def receive(
        self,
        source_code: str,
        raw_body: bytes,
        signature: str | None,
        delivery_id: str | None,
    ) -> EventReceipt:
        """Verify and apply one webhook delivery.

        Raises:
            SourceNotFoundError: No source has ``source_code``.
            SourceInactiveError: The source has been switched off.
            InvalidSignatureError: The signature or delivery id header is
                missing, the signature is wrong, or it is too old.
            InvalidEventError: The body is not a valid event.
            CredentialSourceConflictError: The credential is already
                routed to another source.
        """
        source = await self.sources.get_source(source_code)
        if not source.is_active:
            raise SourceInactiveError(f"Source {source.code} is inactive.")
        self._verify_signature(source, raw_body, signature)
        if not delivery_id:
            raise InvalidSignatureError(
                "The X-EveryCRED-Delivery header is required."
            )
        payload = self._parse(raw_body)

        if await self.events.exists(source.id, delivery_id):
            return EventReceipt(duplicate=True)
        await self._apply(source, payload)
        self.events.add(
            SourceEvent(
                source_id=source.id,
                delivery_id=delivery_id,
                event=payload.event,
            )
        )
        try:
            await self.session.commit()
        except IntegrityError:
            # A concurrent retry of the same delivery committed first.
            await self.session.rollback()
            return EventReceipt(duplicate=True)
        logger.info(
            "Applied %s from source %s (delivery %s)",
            payload.event,
            source.code,
            delivery_id,
        )
        return EventReceipt(duplicate=False)

    def _verify_signature(
        self, source: Source, raw_body: bytes, signature: str | None
    ) -> None:
        secret = self.sources.read_webhook_secret(source)
        if not signature or not is_signature_valid(
            secret,
            signature,
            raw_body,
            self.settings.webhook_tolerance_seconds,
        ):
            logger.warning("Rejected unsigned webhook from %s", source.code)
            raise InvalidSignatureError("The webhook signature is invalid.")

    @staticmethod
    def _parse(raw_body: bytes) -> SourceEventPayload:
        try:
            return SourceEventPayload.model_validate_json(raw_body)
        except ValidationError as exc:
            # Field locations only; values may contain personal data.
            locations = [".".join(map(str, e["loc"])) for e in exc.errors()]
            raise InvalidEventError(
                f"The event is invalid at: {', '.join(locations)}."
            ) from exc

    async def _apply(
        self, source: Source, payload: SourceEventPayload
    ) -> None:
        data = payload.data
        hashed_holder = (
            holder_key(data.holder_email, self.settings)
            if data.holder_email
            else None
        )
        if payload.event.is_credential_event and data.credential_id:
            existing_route = await self.routing.get_route(data.credential_id)
            if (
                existing_route is not None
                and existing_route.source_id != source.id
            ):
                raise CredentialSourceConflictError(
                    f"Credential {data.credential_id} belongs to another "
                    "source."
                )
            await self.routing.save_route(
                credential_id=data.credential_id,
                source_id=source.id,
                holder_key=hashed_holder,
                status=_CREDENTIAL_STATUS_BY_EVENT[payload.event],
            )
        if hashed_holder is None or data.holder_email is None:
            return
        await self.routing.link_holder(hashed_holder, source.id)
        self.notifications.enqueue(
            payload.event,
            {
                "source_code": source.code,
                "holder_email": normalise_email(data.holder_email),
                "credential_id": data.credential_id,
                "request_id": data.request_id,
                "status": data.status,
                "inviter_name": data.inviter_name,
            },
        )

"""Forwarding of credential and request events to the holder service.

Events are written to an outbox in the same transaction that records
them, and the background worker delivers them. A slow or unavailable
holder service therefore never makes a DCS webhook fail, and nothing is
lost if the connector restarts mid-delivery.
"""

import json
import logging
import time
import uuid
from datetime import timedelta
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.encryption import DecryptionError, decrypt_text, encrypt_text
from app.core.models import utc_now
from app.core.signatures import (
    DELIVERY_HEADER,
    EVENT_HEADER,
    SIGNATURE_HEADER,
    encode_body,
    sign,
)
from app.features.notifications.models import (
    HolderNotification,
    NotificationStatus,
)
from app.features.notifications.repository import NotificationRepository

logger = logging.getLogger(__name__)

# Delay before each retry; the last value repeats until attempts run out.
RETRY_DELAYS_SECONDS = (30, 120, 600, 1800, 3600)


def _retry_delay(attempts: int) -> timedelta:
    index = min(attempts - 1, len(RETRY_DELAYS_SECONDS) - 1)
    return timedelta(seconds=RETRY_DELAYS_SECONDS[index])


class NotificationService:
    """Queues events for the holder service and delivers them.

    Attributes:
        session: Unit of work. :meth:`enqueue` leaves committing to the
            caller; :meth:`deliver_due` commits its own batch.
        repository: Persistence for outbox rows.
        http_client: Shared outbound client.
        settings: Holder service URL, secret, and retry limits.
    """

    def __init__(
        self,
        session: AsyncSession,
        http_client: httpx.AsyncClient,
        settings: Settings,
    ) -> None:
        self.session = session
        self.repository = NotificationRepository(session)
        self.http_client = http_client
        self.settings = settings

    @property
    def is_enabled(self) -> bool:
        """Return True when a holder service URL is configured."""
        return self.settings.holder_service_webhook_url is not None

    def enqueue(self, event: str, data: dict[str, Any]) -> None:
        """Stage an event for delivery; the caller commits.

        Does nothing when no holder service URL is configured.
        """
        if not self.is_enabled:
            return
        notification_id = uuid.uuid4()
        payload = {
            "id": notification_id.hex,
            "event": event,
            "created_at": utc_now().isoformat(),
            "data": data,
        }
        self.repository.add(
            HolderNotification(
                id=notification_id,
                event=event,
                encrypted_payload=encrypt_text(
                    json.dumps(payload), self.settings
                ),
            )
        )

    async def deliver_due(self, batch_size: int) -> int:
        """Try every due row once and return how many were delivered."""
        if not self.is_enabled:
            return 0
        due = await self.repository.list_due(utc_now(), batch_size)
        delivered_count = 0
        for notification in due:
            if await self._deliver(notification):
                delivered_count += 1
        await self.session.commit()
        return delivered_count

    async def _deliver(self, notification: HolderNotification) -> bool:
        payload = self._read_payload(notification)
        if payload is None:
            notification.status = NotificationStatus.FAILED
            notification.encrypted_payload = None
            return False
        error, is_retryable = await self._post(notification.event, payload)
        notification.attempts += 1
        if error is None:
            notification.status = NotificationStatus.DELIVERED
            notification.delivered_at = utc_now()
            notification.encrypted_payload = None
            notification.last_error = None
            return True

        notification.last_error = error[:255]
        if (
            not is_retryable
            or notification.attempts >= self.settings.notification_max_attempts
        ):
            notification.status = NotificationStatus.FAILED
            notification.encrypted_payload = None
            logger.error(
                "Gave up delivering notification %s after %s attempts: %s",
                notification.id,
                notification.attempts,
                error,
            )
        else:
            notification.next_attempt_at = utc_now() + _retry_delay(
                notification.attempts
            )
            logger.warning(
                "Delivery of notification %s failed (%s); will retry",
                notification.id,
                error,
            )
        return False

    def _read_payload(
        self, notification: HolderNotification
    ) -> dict[str, Any] | None:
        # A row that cannot be read must fail on its own; raising here
        # would stop every later row in the batch, round after round.
        if notification.encrypted_payload is None:
            return None
        try:
            return json.loads(
                decrypt_text(notification.encrypted_payload, self.settings)
            )
        except (DecryptionError, json.JSONDecodeError):
            logger.error(
                "Notification %s payload is unreadable; marking it failed",
                notification.id,
            )
            notification.last_error = "payload could not be decrypted"
            return None

    async def _post(
        self, event: str, payload: dict[str, Any]
    ) -> tuple[str | None, bool]:
        # Both settings are set together; Settings validates that.
        url = self.settings.holder_service_webhook_url or ""
        secret = self.settings.holder_service_webhook_secret
        body = encode_body(payload)
        headers = {
            "Content-Type": "application/json",
            EVENT_HEADER: event,
            DELIVERY_HEADER: payload["id"],
            SIGNATURE_HEADER: sign(
                secret.get_secret_value() if secret else "",
                int(time.time()),
                body,
            ),
        }
        try:
            response = await self.http_client.post(
                url,
                content=body,
                headers=headers,
                timeout=self.settings.notification_timeout_seconds,
            )
        except httpx.TimeoutException:
            return "timed out", True
        except httpx.HTTPError as exc:
            return type(exc).__name__, True
        if response.is_success:
            return None, False
        # A 4xx other than 408/429 will not fix itself by retrying.
        is_retryable = response.status_code >= 500 or response.status_code in (
            408,
            429,
        )
        return f"holder service answered HTTP {response.status_code}", (
            is_retryable
        )

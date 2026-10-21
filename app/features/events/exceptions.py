"""Errors raised while receiving webhooks from DCS sources."""

from fastapi import status

from app.core.exceptions import AppError, AuthenticationError, ConflictError


class InvalidSignatureError(AuthenticationError):
    """Raised when a webhook's signature is missing, stale, or wrong."""

    error_code = "invalid_signature"
    # Webhook senders do not use bearer tokens.
    headers = None


class InvalidEventError(AppError):
    """Raised when a signed webhook body is not a valid event."""

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    error_code = "invalid_event"


class PayloadTooLargeError(AppError):
    """Raised when a webhook body exceeds the accepted size."""

    status_code = status.HTTP_413_CONTENT_TOO_LARGE
    error_code = "payload_too_large"


class CredentialSourceConflictError(ConflictError):
    """Raised when a source reports a credential another source owns."""

    error_code = "credential_source_conflict"

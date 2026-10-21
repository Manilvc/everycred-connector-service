"""Errors raised while fetching credentials from sources."""

from app.core.exceptions import ExternalServiceError, NotFoundError


class CredentialNotFoundError(NotFoundError):
    """Raised when a credential is unknown, or not the holder's."""

    error_code = "credential_not_found"


class InvalidSourceResponseError(ExternalServiceError):
    """Raised when a source's answer cannot be normalized."""

    error_code = "invalid_source_response"

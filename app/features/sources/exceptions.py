"""Errors raised by the sources feature."""

from app.core.exceptions import (
    AppError,
    ConflictError,
    ExternalServiceError,
    NotFoundError,
)


class SourceNotFoundError(NotFoundError):
    """Raised when no source has the requested code."""

    error_code = "source_not_found"


class SourceCodeTakenError(ConflictError):
    """Raised when a new source reuses an existing code."""

    error_code = "source_code_taken"


class SourceInactiveError(AppError):
    """Raised when a call targets a source that has been switched off."""

    error_code = "source_inactive"


class SourceUnavailableError(ExternalServiceError):
    """Raised when a source cannot be reached or answers with an error."""

    error_code = "source_unavailable"

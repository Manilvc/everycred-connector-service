"""Errors raised while running holder operations."""

from app.core.exceptions import AppError, NotFoundError


class UnknownOperationError(AppError):
    """Raised when the operation name is not in the catalog."""

    error_code = "unknown_operation"


class SourceRequiredError(AppError):
    """Raised when an item operation is called without a source."""

    error_code = "source_required"


class InvalidOperationParamsError(AppError):
    """Raised when params or body do not match the operation."""

    error_code = "invalid_params"


class HolderNotLinkedError(NotFoundError):
    """Raised when the source has never reported the holder."""

    error_code = "holder_not_linked"

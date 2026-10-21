"""Errors raised by the clients feature."""

from app.core.exceptions import NotFoundError


class ClientNotFoundError(NotFoundError):
    """Raised when no client has the requested id."""

    error_code = "client_not_found"

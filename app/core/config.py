"""Service configuration loaded from environment variables.

Every setting the service reads lives on :class:`Settings`. Other modules
call :func:`get_settings` instead of reading ``os.environ`` directly, so
configuration stays in one place and can be overridden in tests.
"""

from enum import StrEnum
from functools import lru_cache
from typing import Annotated, Literal

from cryptography.fernet import Fernet
from fastapi import Depends
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class Environment(StrEnum):
    """Deployment environments the service can run in."""

    LOCAL = "local"
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Runtime settings for the connector service.

    Values are read from environment variables (case-insensitive) and,
    for local development, from a ``.env`` file in the working
    directory. Real environment variables take precedence over ``.env``.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    service_name: str = "everycred-connector-service"
    service_version: str = "0.1.0"
    environment: Environment = Environment.LOCAL

    log_level: LogLevel = "INFO"
    log_json: bool = True

    enable_docs: bool = False
    cors_allowed_origins: list[str] = Field(default_factory=list)

    database_url: SecretStr
    database_pool_size: int = Field(default=5, ge=1)
    database_max_overflow: int = Field(default=10, ge=0)
    database_echo: bool = False
    # MySQL closes idle connections after ``wait_timeout`` (8 hours by
    # default); recycling earlier avoids "server has gone away" errors.
    database_pool_recycle_seconds: int = Field(default=1800, ge=60)

    http_timeout_seconds: float = Field(default=10.0, gt=0)
    http_max_connections: int = Field(default=100, ge=1)

    # Operators manage sources and clients with this key. It is compared
    # in constant time and never stored; rotate it by redeploying.
    admin_api_key: SecretStr = Field(min_length=32)

    # Keys the stored HMAC of client API keys. Changing it invalidates
    # every issued key, so rotate it only together with reissuing them.
    api_key_hash_secret: SecretStr = Field(min_length=32)

    # Keys the HMAC that stands in for a holder's email in the routing
    # table, so the connector can find a holder's credentials without
    # storing the address. Changing it orphans every existing link.
    holder_key_secret: SecretStr = Field(min_length=32)

    # Comma-separated Fernet keys for source API keys and webhook
    # secrets. The first encrypts; all of them are tried when
    # decrypting, so a new key can be put in front of the old one.
    data_encryption_keys: SecretStr

    # Calls to DCS sources. Holder lookups fan out to several sources
    # at once; the limit stops one request from opening too many.
    source_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    source_max_concurrent_calls: int = Field(default=5, ge=1, le=50)

    # Inbound webhooks from DCS sources older than this are rejected,
    # so a captured request cannot be replayed later.
    webhook_tolerance_seconds: int = Field(default=300, ge=30, le=3600)

    # Where credential and request events are forwarded. When the URL
    # is unset, routes are still saved but no notification is queued.
    holder_service_webhook_url: str | None = None
    holder_service_webhook_secret: SecretStr | None = Field(
        default=None, min_length=32
    )
    notification_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    notification_max_attempts: int = Field(default=8, ge=1, le=20)

    # Background worker: notification delivery to the holder service.
    worker_interval_seconds: float = Field(default=5.0, gt=0, le=300)

    @field_validator("data_encryption_keys")
    @classmethod
    def check_encryption_keys(cls, keys: SecretStr) -> SecretStr:
        """Fail at startup if any configured key is not a Fernet key."""
        key_list = [
            key.strip()
            for key in keys.get_secret_value().split(",")
            if key.strip()
        ]
        if not key_list:
            raise ValueError("at least one encryption key is required")
        for key in key_list:
            try:
                Fernet(key)
            except ValueError as exc:
                # The key itself is never echoed into the error.
                raise ValueError(
                    "each key must be a urlsafe base64-encoded 32-byte "
                    "Fernet key"
                ) from exc
        return keys

    @model_validator(mode="after")
    def check_holder_service_webhook(self) -> "Settings":
        """Require a signing secret whenever a holder URL is configured."""
        if self.holder_service_webhook_url is None:
            return self
        if not self.holder_service_webhook_url.startswith(
            ("https://", "http://")
        ):
            raise ValueError("HOLDER_SERVICE_WEBHOOK_URL must be http(s)")
        if self.holder_service_webhook_secret is None:
            raise ValueError(
                "HOLDER_SERVICE_WEBHOOK_SECRET is required when "
                "HOLDER_SERVICE_WEBHOOK_URL is set"
            )
        return self

    @property
    def is_production(self) -> bool:
        """Return True when running in the production environment."""
        return self.environment is Environment.PRODUCTION


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance.

    The result is cached, so the environment is parsed once. Tests that
    change environment variables should call
    ``get_settings.cache_clear()`` afterwards.
    """
    return Settings()


SettingsDep = Annotated[Settings, Depends(get_settings)]

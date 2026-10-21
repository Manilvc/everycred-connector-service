# `app/core/config.py`

> Last updated: 2026-10-21

## Purpose

Loads every runtime setting from environment variables (and from `.env`
in the working directory for local runs) into one typed object. Every
other module reads settings through `get_settings()` or the `SettingsDep`
dependency. Nothing else reads `os.environ` for service settings.

Invalid settings fail at startup. Secrets are typed as `SecretStr`, so
they do not appear in logs or `repr()` output.

## Public API

### `class Settings(BaseSettings)`

The settings model. Field names map to environment variables by
upper-casing the name (`database_url` reads `DATABASE_URL`). Matching is
case-insensitive. Real environment variables take precedence over `.env`.
Unknown variables are ignored.

Full list, with defaults. `(required)` means the service does not start
without the variable.

| Env var | Type | Default | Constraints and notes |
|---|---|---|---|
| `SERVICE_NAME` | str | `everycred-connector-service` | Sent in the `User-Agent` header of outbound calls |
| `SERVICE_VERSION` | str | `0.1.0` | Sent in the `User-Agent` header and the OpenAPI `version` |
| `ENVIRONMENT` | `Environment` | `local` | One of `local`, `development`, `staging`, `production` |
| `LOG_LEVEL` | `LogLevel` | `INFO` | One of `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `LOG_JSON` | bool | `true` | `false` writes plain text lines |
| `ENABLE_DOCS` | bool | `false` | Turns on `/docs`, `/redoc`, `/openapi.json`. Ignored when `ENVIRONMENT=production` |
| `CORS_ALLOWED_ORIGINS` | list[str] | `[]` | JSON list, e.g. `["https://verifier.example.com"]`. Empty disables CORS |
| `DATABASE_URL` | SecretStr | (required) | SQLAlchemy async URL, `mysql+aiomysql://...` |
| `DATABASE_POOL_SIZE` | int | `5` | `>= 1` |
| `DATABASE_MAX_OVERFLOW` | int | `10` | `>= 0` |
| `DATABASE_ECHO` | bool | `false` | Logs every SQL statement when true. Do not enable in production |
| `DATABASE_POOL_RECYCLE_SECONDS` | int | `1800` | `>= 60`. Recycles connections before MySQL's `wait_timeout` closes them |
| `HTTP_TIMEOUT_SECONDS` | float | `10.0` | `> 0`. Default timeout of the shared HTTP client |
| `HTTP_MAX_CONNECTIONS` | int | `100` | `>= 1` |
| `ADMIN_API_KEY` | SecretStr | (required) | `>= 32` characters. Compared with `X-Admin-Key` |
| `API_KEY_HASH_SECRET` | SecretStr | (required) | `>= 32` characters. HMAC key for stored client API key hashes |
| `HOLDER_KEY_SECRET` | SecretStr | (required) | `>= 32` characters. HMAC key for holder identifiers in the routing table |
| `DATA_ENCRYPTION_KEYS` | SecretStr | (required) | Comma-separated Fernet keys. Each key is validated at startup |
| `SOURCE_TIMEOUT_SECONDS` | float | `10.0` | `> 0` and `<= 60`. Timeout per call to a DCS source |
| `SOURCE_MAX_CONCURRENT_CALLS` | int | `5` | `1` to `50`. Concurrency per fan-out request |
| `WEBHOOK_TOLERANCE_SECONDS` | int | `300` | `30` to `3600`. Maximum age of an inbound webhook timestamp |
| `HOLDER_SERVICE_WEBHOOK_URL` | str or None | `None` | Must start with `http://` or `https://`. Setting it requires the secret below |
| `HOLDER_SERVICE_WEBHOOK_SECRET` | SecretStr or None | `None` | `>= 32` characters. Required when the URL is set |
| `NOTIFICATION_TIMEOUT_SECONDS` | float | `10.0` | `> 0` and `<= 60`. Timeout per delivery to the holder service |
| `NOTIFICATION_MAX_ATTEMPTS` | int | `8` | `1` to `20` |
| `WORKER_INTERVAL_SECONDS` | float | `5.0` | `> 0` and `<= 300`. Pause between worker rounds |

Read by other code, outside `Settings`:

| Env var | Read by | Default | Purpose |
|---|---|---|---|
| `DB_WAIT_SECONDS` | `app/core/db_check.py` | `30` | How long the database check retries |
| `WEB_CONCURRENCY` | `deploy/docker-entrypoint.sh` | `2` | Uvicorn worker processes |

### `Settings.is_production` (property)

Returns `True` when `environment` is `production`. Used to switch off
the API docs.

### `get_settings() -> Settings`

Returns the process-wide settings instance. The result is cached with
`lru_cache`, so the environment is parsed once. Tests that change
environment variables call `get_settings.cache_clear()` afterwards.

```python
from app.core.config import get_settings

settings = get_settings()
print(settings.source_timeout_seconds)  # 10.0 with the defaults
```

### `SettingsDep`

`Annotated[Settings, Depends(get_settings)]`. Use it in route and
dependency signatures.

```python
from app.core.config import SettingsDep


async def list_things(settings: SettingsDep) -> None: ...
```

### `Environment` and `LogLevel`

`Environment` is a `StrEnum` of the four deployment names. `LogLevel` is
the `Literal` type of the accepted log level names.

## How it works

1. **Load** — `Settings()` reads the process environment, then `.env`.
   Pydantic applies the types and `Field` constraints.
2. **Validate the keys** — `check_encryption_keys` splits
   `DATA_ENCRYPTION_KEYS` on commas and builds a `Fernet` from each
   entry. A bad key stops startup. The error text does not repeat the key.
3. **Validate the holder service pair** — `check_holder_service_webhook`
   requires the secret whenever the URL is set, and requires the URL
   scheme to be `http` or `https`.
4. **Cache** — `get_settings` wraps the constructor in `lru_cache`.

## Configuration

See the table in [Public API](#class-settingsbasesettings). Sample values
are in [`.env.example`](../../.env.example).

## Failure modes

| Situation | Behaviour | Logged as |
|---|---|---|
| Required variable missing | `ValidationError` when `get_settings()` runs. The process does not start | Not logged; traceback on stderr |
| Malformed Fernet key | `ValidationError` naming the field, not the key | Not logged; traceback on stderr |
| `HOLDER_SERVICE_WEBHOOK_URL` set without a secret | `ValidationError` | Not logged; traceback on stderr |
| Invalid settings during `db_check` | Each problem printed on one line, values hidden | stderr only |

`app/core/db_check.py` prints settings errors in plain form, because
Pydantic's default message echoes the raw input values, secrets included.

## Changing this module

- Add a field to `Settings` with a type, default, and `Field` bounds.
  Add a matching line to `.env.example` and to the table above.
- Secrets must be `SecretStr` and need a minimum length when they key an
  HMAC.
- Read settings only through `get_settings()` or `SettingsDep`. Do not
  call `os.getenv` in feature code.
- Tests set the environment before `app.main` is imported. See
  `tests/conftest.py`.

## Tests

No dedicated test module. `tests/conftest.py` sets every required
variable before the application is imported, so the rest of the suite
runs against a valid `Settings`.

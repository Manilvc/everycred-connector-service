# everycred-connector-service

FastAPI service that routes credential lookups, holder operations, and
events between EveryCRED DCS instances, verifier applications, and the
holder service. Global Python rules in `~/.claude/CLAUDE.md` apply; this
file adds what is specific to this repo.

## Commands

- `uv run pytest` — tests
- `uv run ruff check . && uv run ruff format .` — lint and format
- `uv run fastapi dev` — local server (entrypoint set in `pyproject.toml`)
- `uv run python -m app.worker` — background worker (outbox delivery)
- `uv run alembic upgrade head` — apply migrations
- `uv run alembic revision --autogenerate -m "<change>"` — new migration
- `uv run alembic check` — confirm models and migrations match

Use `uv add <package>` to add dependencies; never edit the dependency
list by hand.

## Structure

Read `docs/README.md` before adding code. In short:

- Features live in `app/features/<name>/` and are mounted in
  `app/api/router.py`.
- Reuse `app/core/`: `DbSession`, `HttpClient`, `AppError` subclasses,
  `get_settings()`, `encrypt_text`/`decrypt_text`, `sign`/
  `is_signature_valid`. Do not create new engines, clients, or settings
  readers.
- Shared validated types (`Identifier`, `HolderEmail`) are in
  `app/shared/identifiers.py`.
- Services commit their own transactions.

## Rules specific to this service

- **No credential storage.** Only routing data (credential id, source,
  status, holder key) is persisted. Never store fetched credential
  contents.
- **No holder emails at rest.** Use `holder_key()` from
  `app/features/routing/holder_keys.py`. The only place an email is
  stored is the encrypted outbox payload, which is cleared on delivery.
- **No arbitrary paths to sources.** Calls to a DCS use fixed templates:
  a normalizer's `credential_path` or an entry in
  `app/features/operations/catalog.py`. Never build a source URL from
  client input other than validated `Identifier` params.
- Source API keys and webhook secrets are Fernet-encrypted
  (`DATA_ENCRYPTION_KEYS`); client API keys are stored as HMACs.
- The DCS side of every endpoint is described in `docs/dcs_contract.md`;
  keep it in sync when operations or events change.

## Database

- MySQL via `aiomysql`; tests use in-memory SQLite, so avoid MySQL-only
  SQL in models.
- Models use `UUIDPrimaryKeyMixin`, `TimestampMixin`, `UTCDateTime`, and
  `enum_values` from `app/core/models.py`.
- Import new models modules in `migrations/env.py` and
  `tests/conftest.py`. Generated migrations must not import `app` code.

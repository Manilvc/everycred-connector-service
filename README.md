# everycred-connector-service

Routes credentials between EveryCRED DCS instances (DCS-India,
DCS-Education, ...) and the applications that use them:

- receives signed **events** from DCS instances when credentials are
  issued or revoked and requests change;
- keeps a **routing table** (credential to source, holder to sources)
  and never stores credential contents;
- answers **verifier** lookups and **holder service** fetches in one
  standard credential format;
- forwards **holder operations** (requests, workflows, KYC, DigiLocker)
  to the right DCS;
- forwards events to the **holder service** as signed webhooks.

Architecture and flows: [`docs/README.md`](docs/README.md). What each
DCS must implement: [`docs/dcs_contract.md`](docs/dcs_contract.md).

## Run locally

Requires Python 3.12+, [uv](https://docs.astral.sh/uv/), and MySQL or
MariaDB.

```bash
cp .env.example .env          # then fill in the secrets and DATABASE_URL
uv sync
uv run alembic upgrade head
uv run fastapi dev            # API on http://127.0.0.1:8000, docs at /docs
uv run python -m app.worker   # in a second terminal
```

Register a source and a client with the operator key:

```bash
curl -X POST http://127.0.0.1:8000/v1/sources \
  -H "X-Admin-Key: <your-admin-key>" -H "Content-Type: application/json" \
  -d '{"code": "dcs-india", "name": "DCS India",
       "base_url": "https://dcs-india.example.com",
       "api_key": "<key-the-dcs-expects>"}'

curl -X POST http://127.0.0.1:8000/v1/clients \
  -H "X-Admin-Key: <your-admin-key>" -H "Content-Type: application/json" \
  -d '{"name": "Holder service", "kind": "holder_service"}'
```

The first answer contains the source's `webhook_secret`, the second the
client's `api_key`; both are shown only once.

## Tests and lint

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

## Docker

```bash
docker compose build
docker compose up -d     # migrate, then api (127.0.0.1:8050) and worker
```

## Configuration

Every variable is listed with its purpose in [`.env.example`](.env.example)
and described in [`docs/core/config.md`](docs/core/config.md).

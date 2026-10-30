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

### Local, with its own MySQL and Adminer

`docker-compose.local.yml` adds a MySQL 8.4 container and Adminer, and
points the app containers at that MySQL. The `DATABASE_URL` in `.env`
cannot be used by containers as-is: inside a container `127.0.0.1` is
the container, not your machine.

1. Set `LOCAL_DB_PASSWORD` in `.env` (hex only, see `.env.example`):

   ```bash
   python -c "import secrets; print(secrets.token_hex(24))"
   ```

2. Start the stack (migrations run first):

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build
   ```

3. Open:

   | What | Where |
   |---|---|
   | API docs | http://127.0.0.1:8050/docs |
   | Adminer | http://127.0.0.1:8081: System `MySQL`, Server `mysql`, Username `connector`, Password `LOCAL_DB_PASSWORD`, Database `everycred_connector` |
   | MySQL from the host | `127.0.0.1:3307` (3306 is left free for a MySQL installed on the host) |

4. Logs, stop, and reset:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.local.yml logs -f api worker
   docker compose -f docker-compose.yml -f docker-compose.local.yml down      # keeps data
   docker compose -f docker-compose.yml -f docker-compose.local.yml down -v   # deletes the local database
   ```

`uv run` on the host keeps using `DATABASE_URL` from `.env`. To point
it at the container database, use `127.0.0.1:3307` with the `connector`
user.

### Server, with an existing MySQL

```bash
docker compose build
docker compose up -d     # migrate, then api (127.0.0.1:8050) and worker
```

`DATABASE_URL` must reach MySQL from inside the containers. For a MySQL
on the same host, prefer its Unix socket: add
`COMPOSE_FILE=docker-compose.yml:docker-compose.mysql-socket.yml` to
`.env` and follow the comments in `docker-compose.mysql-socket.yml`.
Otherwise use `host.docker.internal`, with a user allowed from the
Docker network (`'<user>'@'172.%'`) and MySQL listening beyond
`127.0.0.1`. If the migrate container fails, `docker logs
everycred-connector-migrate` explains the cause and the fix.

## Configuration

Every variable is listed with its purpose in [`.env.example`](.env.example)
and described in [`docs/core/config.md`](docs/core/config.md).

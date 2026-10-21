# `app/core/db_check.py`

> Last updated: 2026-10-21

## Purpose

A command-line check that waits for the database, then exits. It runs
before migrations in the container entrypoint, so a database that is
still starting after a reboot does not produce a driver traceback.
When the check fails, it prints the likely cause and the fix instead.

```bash
uv run python -m app.core.db_check
```

The container runs it before `alembic upgrade head` (see
`deploy/docker-entrypoint.sh`).

## Public API

### `main() -> int`

Entry point. Reads `DB_WAIT_SECONDS` (default `30`) from the environment,
loads settings, and waits for the database. Returns `0` if the database
answered and `1` otherwise.

### `load_settings() -> Settings | None`

Returns `get_settings()`. If validation fails, prints one line per
problem, using the field name in upper case and the reason, and returns
`None`. Values are not printed.

### `wait_for_database(settings: Settings, wait_seconds: float) -> bool`

Tries `SELECT 1` until success or until `wait_seconds` passes. Retries
every `RETRY_DELAY_SECONDS` (2) on `DBAPIError` and `OSError`. On final
failure it prints the target, the URL with the password hidden, the
driver message, and the hints from `explain`.

### `explain(url: URL, error: BaseException) -> list[str]`

Maps the MySQL error number to advice:

| Error number(s) | Meaning | Advice given |
|---|---|---|
| Socket file missing | Socket not mounted | Mount the socket directory, check `@@socket` |
| 2002, 2003, 2005, 2006, 2013 | Cannot connect | Depends on host: `0.0.0.0`, loopback inside a container, `host.docker.internal`, or generic |
| 1045 | Access denied | Check user, password, and percent-encoding |
| 1130 | Host not allowed | Create the user for the Docker network |
| 1049 | Unknown database | `CREATE DATABASE` statement |

### Constants

| Name | Value | Meaning |
|---|---|---|
| `DEFAULT_WAIT_SECONDS` | `30` | Default for `DB_WAIT_SECONDS` |
| `RETRY_DELAY_SECONDS` | `2` | Pause between attempts |
| `CONNECT_TIMEOUT_SECONDS` | `5` | Driver connect timeout per attempt |

## How it works

1. `main` reads `DB_WAIT_SECONDS` directly from `os.environ`. It is not
   a `Settings` field.
2. `load_settings` returns `None` on invalid settings, and `main` exits
   with `1` without trying the database.
3. `wait_for_database` parses the URL with `make_url`, then loops.
4. Each attempt runs `_check_socket` (fails fast when a configured socket
   file is missing) and then `_ping`. `_ping` uses a `NullPool` engine, so
   no connection is kept after the check.
5. On failure it sleeps and retries until the deadline. The last failure
   is explained and printed.

`_in_container` checks for `/.dockerenv`, which changes which hint is
printed for loopback hosts.

## Configuration

| Setting / env var | Default | Effect |
|---|---|---|
| `DB_WAIT_SECONDS` | `30` | Total time to keep retrying |
| `DATABASE_URL` | (required) | Target database |

## Failure modes

| Situation | Behaviour | Exit code |
|---|---|---|
| Database reachable | "Database at ... is reachable." | `0` |
| Database not reachable within the wait | Explanation on stderr | `1` |
| Settings invalid | Each problem on stderr | `1` |

Output goes to stderr only. Nothing is logged through `logging`, so the
check does not need `configure_logging`.

## Changing this module

- Keep the password out of every message. Print `url.render_as_string(
  hide_password=True)`.
- The fallback hint points readers to this document; keep any file a
  hint names present in the repository.
- Keep the exit codes. The entrypoint depends on them.

## Tests

No test module. Run it manually against a known-bad URL to see the
output, for example with `DB_WAIT_SECONDS=3` and a closed port.

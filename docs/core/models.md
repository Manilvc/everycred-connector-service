# `app/core/models.py`

> Last updated: 2026-10-21

## Purpose

Shared column types and mixins for the ORM models in `app/features/*`.
They make three choices consistent across the schema:

- Primary keys are random UUIDs.
- Timestamps are stored and returned as UTC.
- Enum columns store the member's value, not its Python name.

## Public API

### `enum_values(enum_class: type[Enum]) -> list[str]`

Returns each member's `value` as a string. Pass it as `values_callable`
on `sqlalchemy.Enum`, so the database holds `"holder_service"` and not
`HOLDER_SERVICE`.

```python
from sqlalchemy import Enum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import enum_values

kind: Mapped[ClientKind] = mapped_column(
    Enum(ClientKind, native_enum=False, values_callable=enum_values, length=30)
)
```

### `utc_now() -> datetime`

Returns `datetime.now(UTC)`. Use it for every default and every
"now" comparison.

### `class UTCDateTime(TypeDecorator[datetime])`

A `DateTime` column that is always UTC.

- On write, an aware datetime is converted to UTC and saved without
  tzinfo. A naive datetime raises `ValueError`.
- On read, the naive value is returned with `tzinfo=UTC`.

MySQL `DATETIME` has no time zone, so this keeps comparisons with
`utc_now()` safe.

### `class UUIDPrimaryKeyMixin`

Adds `id: Mapped[uuid.UUID]`, a `Uuid` primary key with
`default=uuid.uuid4`.

### `class TimestampMixin`

Adds `created_at` and `updated_at`, both `UTCDateTime`, `NOT NULL`.
`created_at` is set on insert. `updated_at` is set on insert and on every
update.

```python
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.models import TimestampMixin, UUIDPrimaryKeyMixin


class Source(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sources"

    code: Mapped[str] = mapped_column(String(50), unique=True)
```

## How it works

1. **Ids** — `UUIDPrimaryKeyMixin` generates the id in Python before the
   insert, so a new object has its id before it is flushed. Random ids do
   not reveal row counts.
2. **Time** — `TimestampMixin` uses `utc_now` as the Python-side default.
   The database does not compute timestamps.
3. **Time zones** — `UTCDateTime.process_bind_param` converts on the way
   in and `process_result_value` labels on the way out. Application code
   therefore only ever sees aware UTC datetimes.

## Configuration

None. Behaviour is fixed in code.

## Failure modes

| Situation | Behaviour | Logged as |
|---|---|---|
| Naive datetime assigned to a `UTCDateTime` column | `ValueError` during flush. Surfaces as 500 `internal_error` | `ERROR` with traceback |
| Enum value stored that is not in the enum | Read fails with a `LookupError` from SQLAlchemy | `ERROR` with traceback |

## Changing this module

- Every model that stores a time uses `UTCDateTime`, not `DateTime`.
- Keep `enum_values` on every `Enum` column. Changing the stored values
  of an existing enum needs a data migration.
- Mixins only hold columns. Business logic belongs in the feature.
- `Source`, `Client`, `CredentialRoute`, and `HolderNotification` use
  these mixins. `SourceEvent` and `HolderLink` use only
  `UUIDPrimaryKeyMixin` (plus their own timestamps).
- Run `uv run alembic check` after changing a column type.

## Tests

No dedicated module. The mixins are exercised by every feature test that
creates a row, for example `tests/features/clients/test_clients.py`.

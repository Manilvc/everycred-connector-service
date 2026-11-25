"""Create SQLAlchemy engines that are traced even when made after startup.

``SQLAlchemyInstrumentor`` patches ``create_async_engine`` on the
``sqlalchemy.ext.asyncio`` module. A service module that ran
``from sqlalchemy.ext.asyncio import create_async_engine`` before
telemetry started keeps a reference to the original, unpatched
function, so engines it creates later (per-tenant engines, lazily
created global engines) record no query spans. Calling this helper
instead looks the function up on the module at call time and always
gets the patched one.
"""

# fmt: off
# isort: skip_file

from typing import Any

import sqlalchemy.ext.asyncio as sqlalchemy_asyncio


def create_traced_async_engine(*args: Any, **kwargs: Any) -> Any:
    """Create an async engine through the instrumented factory.

    Takes exactly the arguments of
    ``sqlalchemy.ext.asyncio.create_async_engine`` and returns its
    ``AsyncEngine``. While telemetry is off the factory is not patched,
    so this behaves exactly like the plain call.
    """
    return sqlalchemy_asyncio.create_async_engine(*args, **kwargs)

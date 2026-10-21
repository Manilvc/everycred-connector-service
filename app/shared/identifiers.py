"""Validated string types shared by several features.

Identifiers from DCS sources end up in URL paths and logs, so they are
restricted to a safe character set rather than trusted as sent.
"""

from typing import Annotated

from pydantic import Field

IDENTIFIER_PATTERN = r"^[A-Za-z0-9._:-]{1,128}$"
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

Identifier = Annotated[str, Field(pattern=IDENTIFIER_PATTERN)]

HolderEmail = Annotated[
    str,
    Field(
        max_length=320,
        pattern=EMAIL_PATTERN,
        examples=["holder@example.com"],
    ),
]

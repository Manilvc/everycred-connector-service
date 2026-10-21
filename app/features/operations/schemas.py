"""Request and response models for holder operations."""

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from app.features.sources.schemas import SourceCode
from app.shared.identifiers import HolderEmail, Identifier


class HolderOperationRequest(BaseModel):
    """Run one catalog operation for a holder."""

    model_config = ConfigDict(extra="forbid")

    holder_email: HolderEmail
    operation: str = Field(max_length=50, examples=["requests.get"])
    source_code: SourceCode | None = Field(
        default=None,
        description=(
            "Required except for fan-out operations, which call every "
            "source the holder is linked to when it is omitted."
        ),
    )
    params: dict[Annotated[str, Field(max_length=30)], Identifier] = Field(
        default_factory=dict, max_length=10
    )
    body: dict[str, Any] | None = None


class OperationResult(BaseModel):
    """What one source answered."""

    source_code: str
    status_code: int
    ok: bool
    data: Any = None
    message: str | None = None


class HolderOperationResponse(BaseModel):
    """Answers from every source the operation was sent to."""

    items: list[OperationResult]

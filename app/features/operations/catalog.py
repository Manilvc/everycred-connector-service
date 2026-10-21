"""Holder operations the connector forwards to DCS sources.

The holder service asks for an operation by name; it never supplies a
path. Each operation fixes the HTTP method, the path template below the
source's holder API, the path parameters it accepts, and whether it may
carry a body or fan out to every source the holder is linked to. Adding
an operation here is the only way to widen what the holder service can
reach in a DCS.

All paths are relative to :data:`DCS_HOLDER_API_PREFIX`, the internal
holder API every DCS source must expose (see ``docs/dcs_contract.md``).
"""

from dataclasses import dataclass
from urllib.parse import quote

DCS_HOLDER_API_PREFIX = "/v1/internal/holder"

_WORKFLOW_REQUEST = "/workflow-requests/{request_uuid}"
_INTEGRATION_STEP = (
    "/requests/{request_id}/integration/{integration_type}/{tool_code}/{flow}"
)
_INTEGRATION_STEP_PARAMS = (
    "request_id",
    "integration_type",
    "tool_code",
    "flow",
)


@dataclass(frozen=True, slots=True)
class HolderOperation:
    """One allowed call from the holder service into a DCS source.

    Attributes:
        name: Identifier the holder service uses, e.g. "requests.get".
        method: HTTP method sent to the source.
        path_template: Path with ``{param}`` placeholders.
        param_names: Placeholders the caller must fill, no more, no less.
        has_body: Whether a JSON body is forwarded.
        is_fan_out: Whether the call goes to every linked source when no
            source is named.
    """

    name: str
    method: str
    path_template: str
    param_names: tuple[str, ...] = ()
    has_body: bool = False
    is_fan_out: bool = False

    def build_path(self, params: dict[str, str]) -> str:
        """Return the full path with ``params`` URL-encoded into it."""
        encoded_params = {
            name: quote(value, safe="") for name, value in params.items()
        }
        return DCS_HOLDER_API_PREFIX + self.path_template.format(
            **encoded_params
        )


_OPERATIONS = (
    HolderOperation("requests.list", "GET", "/requests", is_fan_out=True),
    HolderOperation(
        "requests.get", "GET", "/requests/{request_id}", ("request_id",)
    ),
    HolderOperation(
        "requests.fields",
        "GET",
        "/requests/{request_id}/fields",
        ("request_id",),
    ),
    HolderOperation(
        "requests.submit",
        "POST",
        "/requests/{request_id}/submission",
        ("request_id",),
        has_body=True,
    ),
    HolderOperation(
        "requests.decline",
        "POST",
        "/requests/{request_id}/decline",
        ("request_id",),
        has_body=True,
    ),
    HolderOperation("kyc.detail", "GET", "/kyc-detail"),
    HolderOperation(
        "workflow.list", "GET", "/workflow-requests", is_fan_out=True
    ),
    HolderOperation(
        "workflow.get", "GET", _WORKFLOW_REQUEST, ("request_uuid",)
    ),
    HolderOperation(
        "workflow.consent",
        "POST",
        f"{_WORKFLOW_REQUEST}/consent",
        ("request_uuid",),
        has_body=True,
    ),
    HolderOperation(
        "workflow.node_submit",
        "POST",
        f"{_WORKFLOW_REQUEST}/nodes/{{node_key}}/submit",
        ("request_uuid", "node_key"),
        has_body=True,
    ),
    HolderOperation(
        "workflow.node_accept",
        "POST",
        f"{_WORKFLOW_REQUEST}/nodes/{{node_key}}/accept",
        ("request_uuid", "node_key"),
        has_body=True,
    ),
    HolderOperation(
        "workflow.node_decline",
        "POST",
        f"{_WORKFLOW_REQUEST}/nodes/{{node_key}}/decline",
        ("request_uuid", "node_key"),
        has_body=True,
    ),
    HolderOperation(
        "integrations.list",
        "GET",
        "/requests/{request_id}/integration",
        ("request_id",),
    ),
    HolderOperation(
        "integrations.start",
        "POST",
        f"{_INTEGRATION_STEP}/start",
        _INTEGRATION_STEP_PARAMS,
        has_body=True,
    ),
    HolderOperation(
        "integrations.inputs",
        "POST",
        f"{_INTEGRATION_STEP}/inputs",
        _INTEGRATION_STEP_PARAMS,
        has_body=True,
    ),
    HolderOperation(
        "integrations.cancel",
        "POST",
        f"{_INTEGRATION_STEP}/cancel",
        _INTEGRATION_STEP_PARAMS,
        has_body=True,
    ),
    HolderOperation(
        "digilocker.initialize",
        "POST",
        "/digilocker/initialize",
        has_body=True,
    ),
    HolderOperation(
        "digilocker.complete",
        "GET",
        "/digilocker/complete-flow/{client_id}",
        ("client_id",),
    ),
    HolderOperation(
        "credentials.stats",
        "GET",
        "/credentials/{credential_id}/stats",
        ("credential_id",),
    ),
)

OPERATIONS_BY_NAME = {operation.name: operation for operation in _OPERATIONS}

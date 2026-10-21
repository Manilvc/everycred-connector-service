import pytest

from app.normalizers.base import NormalizationError, get_source_format
from app.normalizers.everycred_dcs import normalize_everycred_dcs
from tests.helpers import dcs_credential_body


def test_dcs_format_builds_the_verifier_path() -> None:
    source_format = get_source_format("everycred_dcs")

    assert source_format.build_credential_path("abc") == (
        "/v1/user/credential/abc"
    )


def test_empty_strings_become_null() -> None:
    credential = normalize_everycred_dcs(dcs_credential_body(), "c1", "dcs")

    assert credential.issuer.email is None
    assert credential.issuer.name == "Example University"
    assert credential.fields == {"grade": "A"}


def test_unparseable_credential_json_is_dropped() -> None:
    body = dcs_credential_body()
    body["data"]["credential_json_content"] = "{not json"

    credential = normalize_everycred_dcs(body, "c1", "dcs")

    assert credential.credential_json is None


def test_missing_data_raises() -> None:
    with pytest.raises(NormalizationError):
        normalize_everycred_dcs({"status": "fail", "data": None}, "c1", "dcs")

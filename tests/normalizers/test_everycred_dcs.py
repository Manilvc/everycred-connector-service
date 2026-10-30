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


def test_validity_and_raw_document_come_from_the_credential() -> None:
    body = dcs_credential_body()

    credential = normalize_everycred_dcs(body, "c1", "dcs")

    assert credential.credential_unique_id == "unique-1"
    assert credential.subject_name == "Computer Science"
    assert credential.subject_logo_url == "https://cdn.example.com/subject.png"
    assert credential.valid_from == "2026-10-01T00:00:00Z"
    assert credential.valid_until == "2030-10-01T00:00:00Z"
    # Kept byte for byte so proofs can be checked against it.
    assert (
        credential.credential_json_content
        == body["data"]["credential_json_content"]
    )


def test_vc_1_1_dates_are_used_when_2_0_names_are_absent() -> None:
    body = dcs_credential_body()
    body["data"]["credential_json_content"] = (
        '{"issuanceDate": "2025-01-01T00:00:00Z", '
        '"expirationDate": "2027-01-01T00:00:00Z"}'
    )

    credential = normalize_everycred_dcs(body, "c1", "dcs")

    assert credential.valid_from == "2025-01-01T00:00:00Z"
    assert credential.valid_until == "2027-01-01T00:00:00Z"


def test_analytics_path_encodes_the_id() -> None:
    source_format = get_source_format("everycred_dcs")

    assert source_format.build_verification_analytics_path("a b") == (
        "/v1/credential/verification/analytics?uuid=a%20b"
    )

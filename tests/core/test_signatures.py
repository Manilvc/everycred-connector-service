from app.core.signatures import encode_body, is_signature_valid, sign

SECRET = "whsec_test"
BODY = encode_body({"b": 1, "a": "x"})


def test_body_encoding_is_canonical() -> None:
    assert BODY == b'{"a":"x","b":1}'


def test_fresh_signature_is_valid() -> None:
    header = sign(SECRET, 1_000, BODY)

    assert is_signature_valid(SECRET, header, BODY, 300, now=1_100)


def test_tampered_body_is_invalid() -> None:
    header = sign(SECRET, 1_000, BODY)

    assert not is_signature_valid(SECRET, header, BODY + b" ", 300, now=1_000)


def test_old_signature_is_invalid() -> None:
    header = sign(SECRET, 1_000, BODY)

    assert not is_signature_valid(SECRET, header, BODY, 300, now=1_301)


def test_malformed_header_is_invalid() -> None:
    assert not is_signature_valid(SECRET, "v1=abc", BODY, 300, now=1_000)
    assert not is_signature_valid(SECRET, "t=x,v1=abc", BODY, 300, now=1)

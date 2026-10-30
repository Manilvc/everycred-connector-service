import pytest
from cryptography.fernet import Fernet
from httpx import AsyncClient

from app.core.config import get_settings
from app.core.encryption import DecryptionError, decrypt_text, encrypt_text
from app.core.security import (
    extract_api_key_prefix,
    generate_api_key,
    is_api_key_valid,
)


def test_encrypted_text_round_trips() -> None:
    settings = get_settings()

    ciphertext = encrypt_text("source-api-key", settings)

    assert ciphertext != "source-api-key"
    assert decrypt_text(ciphertext, settings) == "source-api-key"


def test_text_from_another_key_cannot_be_decrypted() -> None:
    foreign = Fernet(Fernet.generate_key()).encrypt(b"x").decode()

    with pytest.raises(DecryptionError):
        decrypt_text(foreign, get_settings())


def test_generated_api_key_verifies_against_its_hash() -> None:
    settings = get_settings()

    generated = generate_api_key(settings)

    assert extract_api_key_prefix(generated.plaintext) == generated.prefix
    assert is_api_key_valid(generated.plaintext, generated.key_hash, settings)
    assert not is_api_key_valid(
        generated.plaintext + "x", generated.key_hash, settings
    )


@pytest.mark.parametrize(
    "api_key",
    ["", "ecc_short_x", "eci_000000000000_secret", "ecc_000000000000_"],
)
def test_malformed_api_keys_have_no_prefix(api_key: str) -> None:
    assert extract_api_key_prefix(api_key) is None


async def test_openapi_documents_admin_and_client_keys_separately(
    client: AsyncClient,
) -> None:
    response = await client.get("/openapi.json")

    schema = response.json()
    assert schema["components"]["securitySchemes"] == {
        "AdminKey": {"type": "apiKey", "in": "header", "name": "X-Admin-Key"},
        "ClientKey": {"type": "apiKey", "in": "header", "name": "X-API-Key"},
    }
    assert schema["paths"]["/v1/clients"]["post"]["security"] == [
        {"AdminKey": []}
    ]

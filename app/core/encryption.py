"""Encryption of secrets stored in the database.

Source API keys and webhook signing secrets must be readable by the
service (it sends and verifies them), so they are encrypted rather than
hashed. Fernet (AES-128-CBC with an HMAC-SHA256 signature) means a
stored value can be neither read nor altered without the key.
:class:`~cryptography.fernet.MultiFernet` allows key rotation: the first
configured key encrypts, and every key is tried when decrypting.
"""

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.core.config import Settings


class DecryptionError(Exception):
    """Raised when stored ciphertext cannot be decrypted.

    Either the data was tampered with, or it was encrypted with a key
    that is no longer configured.
    """


@lru_cache(maxsize=4)
def _build_cipher(serialised_keys: str) -> MultiFernet:
    keys = [key.strip() for key in serialised_keys.split(",") if key.strip()]
    return MultiFernet([Fernet(key) for key in keys])


def _cipher(settings: Settings) -> MultiFernet:
    return _build_cipher(settings.data_encryption_keys.get_secret_value())


def encrypt_text(plaintext: str, settings: Settings) -> str:
    """Return ``plaintext`` encrypted with the current key."""
    return _cipher(settings).encrypt(plaintext.encode()).decode()


def decrypt_text(ciphertext: str, settings: Settings) -> str:
    """Decrypt a value produced by :func:`encrypt_text`.

    Raises:
        DecryptionError: The ciphertext is invalid or no configured key
            can decrypt it.
    """
    try:
        return _cipher(settings).decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise DecryptionError("Stored value could not be decrypted.") from exc

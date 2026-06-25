import pytest
from cryptography.fernet import Fernet

from app.infrastructure.fernet_key_cipher import FernetKeyCipher


def _cipher() -> FernetKeyCipher:
    return FernetKeyCipher(Fernet.generate_key().decode())


def test_encrypt_does_not_expose_the_plaintext():
    cipher = _cipher()

    token = cipher.encrypt("sk-secret-value-1234")

    assert "sk-secret-value-1234" not in token


def test_decrypt_recovers_the_original_key():
    cipher = _cipher()

    token = cipher.encrypt("sk-secret-value-1234")

    assert cipher.decrypt(token) == "sk-secret-value-1234"


def test_two_encryptions_of_the_same_key_differ():
    cipher = _cipher()

    assert cipher.encrypt("sk-same") != cipher.encrypt("sk-same")


def test_decrypt_rejects_a_token_from_a_different_secret():
    token = _cipher().encrypt("sk-secret")

    with pytest.raises(Exception):
        _cipher().decrypt(token)


def test_decrypt_rejects_a_tampered_token():
    cipher = _cipher()
    token = cipher.encrypt("sk-secret")
    # Flip a character in the ciphertext body so the HMAC no longer matches.
    flipped = "A" if token[20] != "A" else "B"
    tampered = token[:20] + flipped + token[21:]

    with pytest.raises(Exception):
        cipher.decrypt(tampered)

from cryptography.fernet import Fernet

from app.application.ports import KeyCipher


class FernetKeyCipher(KeyCipher):
    """Symmetric authenticated encryption (Fernet: AES-128-CBC + HMAC-SHA256) for
    secrets the server must replay, such as provider API keys. The Fernet secret is
    supplied from outside the database (env/KMS); ciphertext is the only thing stored."""

    def __init__(self, secret: str) -> None:
        self._fernet = Fernet(secret)

    def encrypt(self, plain: str) -> str:
        return self._fernet.encrypt(plain.encode()).decode()

    def decrypt(self, token: str) -> str:
        return self._fernet.decrypt(token.encode()).decode()

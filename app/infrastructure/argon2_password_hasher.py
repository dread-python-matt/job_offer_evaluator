from argon2 import PasswordHasher as _Argon2
from argon2.exceptions import Argon2Error, InvalidHashError

from app.application.ports import PasswordHasher


class Argon2PasswordHasher(PasswordHasher):
    """Argon2id password hashing (the current OWASP-recommended default). Salting and
    parameter encoding are handled by argon2-cffi, so each hash is self-describing and
    verifiable without storing parameters separately."""

    def __init__(self) -> None:
        self._hasher = _Argon2()

    def hash(self, plain: str) -> str:
        return self._hasher.hash(plain)

    def verify(self, plain: str, hashed: str) -> bool:
        try:
            return self._hasher.verify(hashed, plain)
        except (Argon2Error, InvalidHashError):
            # Wrong password, or a malformed/unsupported hash — all treated as "not verified".
            # (InvalidHashError is a ValueError, outside the Argon2Error hierarchy.)
            return False

from datetime import datetime, timezone

from cryptography.fernet import Fernet

from app.application.admin_key_resolver import AdminKeyResolver
from app.application.ports import AdminKeyRecord
from app.infrastructure.fernet_key_cipher import FernetKeyCipher
from tests.fakes import InMemoryAdminKeyRepository


def _cipher() -> FernetKeyCipher:
    return FernetKeyCipher(Fernet.generate_key().decode())


def test_returns_none_when_the_user_has_no_admin_key():
    resolver = AdminKeyResolver(InMemoryAdminKeyRepository(), _cipher())

    assert resolver.key_for_user("user-1") is None


def test_returns_the_decrypted_key_when_the_user_has_one():
    repo = InMemoryAdminKeyRepository()
    cipher = _cipher()
    repo.upsert(
        AdminKeyRecord(
            user_id="user-1",
            key_ciphertext=cipher.encrypt("sk-admin-secret"),
            key_hint="sk-…cret",
            created_at=datetime(2026, 6, 30, tzinfo=timezone.utc),
        )
    )

    resolver = AdminKeyResolver(repo, cipher)

    assert resolver.key_for_user("user-1") == "sk-admin-secret"

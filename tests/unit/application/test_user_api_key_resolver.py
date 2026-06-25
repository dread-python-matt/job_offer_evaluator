from datetime import datetime, timezone

import pytest
from cryptography.fernet import Fernet

from app.application.api_key_resolver import UserApiKeyResolver
from app.application.ports import ApiKeyRecord
from app.domain.errors import MissingProviderApiKeyError
from app.infrastructure.fernet_key_cipher import FernetKeyCipher
from tests.fakes import InMemoryApiKeyRepository

_NOW = datetime(2026, 6, 25, tzinfo=timezone.utc)


def _resolver_with(repo, cipher):
    return UserApiKeyResolver(repo, cipher)


def test_returns_the_decrypted_key_for_a_stored_provider():
    cipher = FernetKeyCipher(Fernet.generate_key().decode())
    repo = InMemoryApiKeyRepository()
    repo.add(
        ApiKeyRecord(
            user_id="u1",
            api_provider="openai",
            key_ciphertext=cipher.encrypt("sk-secret"),
            key_hint="sk-…cret",
            limit_usd=5.0,
            tracking_since=_NOW,
            created_at=_NOW,
        )
    )

    assert _resolver_with(repo, cipher).key_for_provider("u1", "openai") == "sk-secret"


def test_raises_when_the_user_has_no_key_for_the_provider():
    cipher = FernetKeyCipher(Fernet.generate_key().decode())

    with pytest.raises(MissingProviderApiKeyError):
        _resolver_with(InMemoryApiKeyRepository(), cipher).key_for_provider("u1", "openai")

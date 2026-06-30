from datetime import datetime, timezone

import pytest
from cryptography.fernet import Fernet

from app.application.admin_key_use_cases import (
    DeleteAdminKeyUseCase,
    GetAdminKeyUseCase,
    SetAdminKeyUseCase,
)
from app.domain.errors import InvalidAdminKeyError
from app.infrastructure.fernet_key_cipher import FernetKeyCipher
from tests.fakes import FakeAdminKeyValidator, InMemoryAdminKeyRepository

_NOON = datetime(2026, 6, 30, 12, tzinfo=timezone.utc)
_KEY = "sk-admin-abcdEFGH1234"


def _cipher() -> FernetKeyCipher:
    return FernetKeyCipher(Fernet.generate_key().decode())


def test_set_validates_then_stores_only_ciphertext_and_a_masked_hint():
    repo = InMemoryAdminKeyRepository()
    cipher = _cipher()
    validator = FakeAdminKeyValidator()
    use_case = SetAdminKeyUseCase(repo, cipher, validator, clock=lambda: _NOON)

    view = use_case.execute("user-1", _KEY)

    assert validator.validated == [_KEY]
    assert view.key_hint == "sk-…1234"
    assert view.created_at == _NOON
    stored = repo.get("user-1")
    assert stored is not None
    # The plaintext key is never stored; only its ciphertext, which round-trips.
    assert stored.key_ciphertext != _KEY
    assert cipher.decrypt(stored.key_ciphertext) == _KEY


def test_set_rejects_an_invalid_key_without_storing_it():
    repo = InMemoryAdminKeyRepository()
    use_case = SetAdminKeyUseCase(repo, _cipher(), FakeAdminKeyValidator(reject={_KEY}))

    with pytest.raises(InvalidAdminKeyError):
        use_case.execute("user-1", _KEY)

    assert repo.get("user-1") is None


def test_set_replaces_an_existing_key_rather_than_erroring():
    repo = InMemoryAdminKeyRepository()
    cipher = _cipher()
    use_case = SetAdminKeyUseCase(repo, cipher, FakeAdminKeyValidator(), clock=lambda: _NOON)

    use_case.execute("user-1", "sk-old-key-0000")
    use_case.execute("user-1", _KEY)

    stored = repo.get("user-1")
    assert cipher.decrypt(stored.key_ciphertext) == _KEY


def test_get_returns_none_when_no_key_is_saved():
    assert GetAdminKeyUseCase(InMemoryAdminKeyRepository()).execute("user-1") is None


def test_get_returns_the_masked_view_when_a_key_is_saved():
    repo = InMemoryAdminKeyRepository()
    cipher = _cipher()
    SetAdminKeyUseCase(repo, cipher, FakeAdminKeyValidator(), clock=lambda: _NOON).execute(
        "user-1", _KEY
    )

    view = GetAdminKeyUseCase(repo).execute("user-1")

    assert view is not None
    assert view.key_hint == "sk-…1234"


def test_delete_reports_whether_a_key_was_removed_and_is_idempotent():
    repo = InMemoryAdminKeyRepository()
    SetAdminKeyUseCase(repo, _cipher(), FakeAdminKeyValidator()).execute("user-1", _KEY)
    use_case = DeleteAdminKeyUseCase(repo)

    assert use_case.execute("user-1") is True
    assert use_case.execute("user-1") is False  # nothing left to delete
    assert repo.get("user-1") is None

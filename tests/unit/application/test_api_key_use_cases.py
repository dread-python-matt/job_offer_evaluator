from datetime import datetime, timezone

import pytest

from app.application.api_key_use_cases import (
    AddApiKeyUseCase,
    ApiKeyView,
    DeleteApiKeyUseCase,
    ListApiKeysUseCase,
    SetApiKeyBudgetUseCase,
    SetDailyRequestLimitUseCase,
)
from app.application.ports import ApiKeyValidator, UserProviderSpendProvider
from app.domain.errors import (
    ApiKeyAlreadyExistsError,
    ApiKeyNotFoundError,
    InvalidApiKeyError,
    UnsupportedApiProviderError,
)
from app.infrastructure.fernet_key_cipher import FernetKeyCipher
from cryptography.fernet import Fernet
from tests.fakes import InMemoryApiKeyRepository

_USER = "user-1"
_NOW = datetime(2026, 6, 25, tzinfo=timezone.utc)


class _AcceptingValidator(ApiKeyValidator):
    def __init__(self):
        self.validated = []

    def validate(self, provider, key):
        self.validated.append((provider, key))


class _RejectingValidator(ApiKeyValidator):
    def validate(self, provider, key):
        raise InvalidApiKeyError(provider)


class _FixedProviderSpend(UserProviderSpendProvider):
    def __init__(self, by_company=None):
        self._by_company = by_company or {}

    def spend_since(self, user_id, company, start):
        return self._by_company.get(company, 0.0)


def _cipher():
    return FernetKeyCipher(Fernet.generate_key().decode())


def _add_use_case(repo, cipher, validator=None):
    return AddApiKeyUseCase(
        repo, cipher, validator or _AcceptingValidator(), clock=lambda: _NOW
    )


# --- AddApiKeyUseCase ---


def test_add_stores_an_encrypted_key_and_returns_a_masked_view():
    repo, cipher = InMemoryApiKeyRepository(), _cipher()

    view = _add_use_case(repo, cipher).execute(
        _USER, "openai", "sk-secret-value-1234", 10.0
    )

    assert view == ApiKeyView(
        api_provider="openai", key_hint="sk-…1234", limit_usd=10.0, used_usd=0.0
    )
    stored = repo.get(_USER, "openai")
    assert stored.key_ciphertext != "sk-secret-value-1234"
    assert cipher.decrypt(stored.key_ciphertext) == "sk-secret-value-1234"


def test_add_google_key_defaults_to_a_zero_usd_limit():
    # Google keys are request-budgeted (per-day), not dollar-budgeted, so adding one needn't
    # carry a USD limit — it defaults to 0.
    repo, cipher = InMemoryApiKeyRepository(), _cipher()

    view = _add_use_case(repo, cipher).execute(_USER, "google", "AIza-google-key-7890")

    assert view.limit_usd == 0.0
    assert repo.get(_USER, "google").limit_usd == 0.0


def test_add_validates_the_key_before_storing():
    repo, cipher = InMemoryApiKeyRepository(), _cipher()
    validator = _AcceptingValidator()

    _add_use_case(repo, cipher, validator).execute(_USER, "openai", "sk-good", 5.0)

    assert validator.validated == [("openai", "sk-good")]


def test_add_rejected_key_is_not_stored():
    repo, cipher = InMemoryApiKeyRepository(), _cipher()

    with pytest.raises(InvalidApiKeyError):
        AddApiKeyUseCase(
            repo, cipher, _RejectingValidator(), clock=lambda: _NOW
        ).execute(_USER, "openai", "sk-bad", 5.0)

    assert repo.get(_USER, "openai") is None


def test_add_rejects_an_unsupported_provider():
    repo, cipher = InMemoryApiKeyRepository(), _cipher()

    with pytest.raises(UnsupportedApiProviderError):
        _add_use_case(repo, cipher).execute(_USER, "anthropic", "sk-x", 5.0)


def test_add_rejects_a_duplicate_provider():
    repo, cipher = InMemoryApiKeyRepository(), _cipher()
    _add_use_case(repo, cipher).execute(_USER, "openai", "sk-one", 5.0)

    with pytest.raises(ApiKeyAlreadyExistsError):
        _add_use_case(repo, cipher).execute(_USER, "openai", "sk-two", 5.0)


def test_add_signals_a_key_change_for_the_user_after_storing():
    # Lets derived per-user state (e.g. the cached model picker) refresh immediately.
    repo, cipher = InMemoryApiKeyRepository(), _cipher()
    changed = []

    AddApiKeyUseCase(
        repo,
        cipher,
        _AcceptingValidator(),
        clock=lambda: _NOW,
        on_change=changed.append,
    ).execute(_USER, "openai", "sk-good", 5.0)

    assert changed == [_USER]


def test_add_does_not_signal_a_change_when_the_key_is_rejected():
    repo, cipher = InMemoryApiKeyRepository(), _cipher()
    changed = []

    with pytest.raises(InvalidApiKeyError):
        AddApiKeyUseCase(
            repo,
            cipher,
            _RejectingValidator(),
            clock=lambda: _NOW,
            on_change=changed.append,
        ).execute(_USER, "openai", "sk-bad", 5.0)

    assert changed == []


# --- ListApiKeysUseCase ---


def test_list_returns_each_key_with_derived_usage():
    repo, cipher = InMemoryApiKeyRepository(), _cipher()
    _add_use_case(repo, cipher).execute(_USER, "openai", "sk-openai-key-1234", 10.0)
    _add_use_case(repo, cipher).execute(_USER, "google", "AIza-google-key-7890", 8.0)
    spend = _FixedProviderSpend({"OpenAI": 3.5, "Google": 1.0})

    views = ListApiKeysUseCase(repo, spend).execute(_USER)

    assert ApiKeyView("openai", "sk-…1234", 10.0, 3.5) in views
    assert ApiKeyView("google", "AIz…7890", 8.0, 1.0) in views


def test_list_never_exposes_ciphertext_or_plaintext():
    repo, cipher = InMemoryApiKeyRepository(), _cipher()
    _add_use_case(repo, cipher).execute(_USER, "openai", "sk-openai-key-1234", 10.0)

    [view] = ListApiKeysUseCase(repo, _FixedProviderSpend()).execute(_USER)

    assert not hasattr(view, "key_ciphertext")
    assert "sk-openai-key-1234" not in repr(view)


# --- SetApiKeyBudgetUseCase ---


def test_set_budget_updates_the_limit_and_returns_the_view():
    repo, cipher = InMemoryApiKeyRepository(), _cipher()
    _add_use_case(repo, cipher).execute(_USER, "openai", "sk-openai-key-1234", 10.0)
    spend = _FixedProviderSpend({"OpenAI": 2.0})

    view = SetApiKeyBudgetUseCase(repo, spend).execute(_USER, "openai", 25.0)

    assert view == ApiKeyView("openai", "sk-…1234", 25.0, 2.0)
    assert repo.get(_USER, "openai").limit_usd == 25.0


def test_set_budget_on_a_missing_key_raises():
    repo = InMemoryApiKeyRepository()

    with pytest.raises(ApiKeyNotFoundError):
        SetApiKeyBudgetUseCase(repo, _FixedProviderSpend()).execute(
            _USER, "openai", 25.0
        )


class _RowVanishesAfterUpdate(InMemoryApiKeyRepository):
    """Models the rare race where the budget update matches a row but it's deleted before the
    follow-up read: update_budget → True, then get → None."""

    def update_budget(self, user_id, api_provider, limit_usd):
        return True

    def get(self, user_id, api_provider):
        return None


def test_set_budget_raises_not_found_when_the_row_vanishes_after_the_update():
    # Guards against dereferencing None into a 500 (L-2): a concurrent delete between the
    # update and the read surfaces as a clean ApiKeyNotFoundError (404), not a crash.
    use_case = SetApiKeyBudgetUseCase(_RowVanishesAfterUpdate(), _FixedProviderSpend())

    with pytest.raises(ApiKeyNotFoundError):
        use_case.execute(_USER, "openai", 25.0)


# --- SetDailyRequestLimitUseCase ---


def test_set_daily_request_limit_stores_an_override():
    repo, cipher = InMemoryApiKeyRepository(), _cipher()
    _add_use_case(repo, cipher).execute(_USER, "google", "AIza-google-key-7890", 8.0)

    SetDailyRequestLimitUseCase(repo).execute(_USER, "google", 50)

    assert repo.get(_USER, "google").daily_request_limit == 50


def test_set_daily_request_limit_to_none_clears_the_override():
    repo, cipher = InMemoryApiKeyRepository(), _cipher()
    _add_use_case(repo, cipher).execute(_USER, "google", "AIza-google-key-7890", 8.0)
    SetDailyRequestLimitUseCase(repo).execute(_USER, "google", 50)

    SetDailyRequestLimitUseCase(repo).execute(_USER, "google", None)

    assert repo.get(_USER, "google").daily_request_limit is None


def test_set_daily_request_limit_on_a_missing_key_raises():
    with pytest.raises(ApiKeyNotFoundError):
        SetDailyRequestLimitUseCase(InMemoryApiKeyRepository()).execute(
            _USER, "google", 50
        )


# --- DeleteApiKeyUseCase ---


def test_delete_removes_the_key():
    repo, cipher = InMemoryApiKeyRepository(), _cipher()
    _add_use_case(repo, cipher).execute(_USER, "openai", "sk-openai-key-1234", 10.0)

    DeleteApiKeyUseCase(repo).execute(_USER, "openai")

    assert repo.get(_USER, "openai") is None


def test_delete_a_missing_key_raises():
    with pytest.raises(ApiKeyNotFoundError):
        DeleteApiKeyUseCase(InMemoryApiKeyRepository()).execute(_USER, "openai")


def test_delete_signals_a_key_change_for_the_user():
    repo, cipher = InMemoryApiKeyRepository(), _cipher()
    _add_use_case(repo, cipher).execute(_USER, "openai", "sk-openai-key-1234", 10.0)
    changed = []

    DeleteApiKeyUseCase(repo, on_change=changed.append).execute(_USER, "openai")

    assert changed == [_USER]


def test_delete_a_missing_key_does_not_signal_a_change():
    changed = []

    with pytest.raises(ApiKeyNotFoundError):
        DeleteApiKeyUseCase(
            InMemoryApiKeyRepository(), on_change=changed.append
        ).execute(_USER, "openai")

    assert changed == []

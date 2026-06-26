from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet

from app.application.ports import ApiKeyRecord, AvailableModel, AvailableModelsProvider
from app.infrastructure.fernet_key_cipher import FernetKeyCipher
from app.infrastructure.keyed_user_available_models_provider import (
    CachingUserAvailableModelsProvider,
    KeyedUserAvailableModelsProvider,
)
from tests.fakes import InMemoryApiKeyRepository

_NOW = datetime(2026, 6, 25, tzinfo=timezone.utc)


class _StubProvider(AvailableModelsProvider):
    def __init__(self, models=None, error=None):
        self._models = models or []
        self._error = error
        self.calls = 0

    def list_models(self):
        self.calls += 1
        if self._error is not None:
            raise self._error
        return self._models


def _repo_with(cipher, *keys):
    repo = InMemoryApiKeyRepository()
    for provider in keys:
        repo.add(
            ApiKeyRecord(
                user_id="u1",
                api_provider=provider,
                key_ciphertext=cipher.encrypt(f"key-{provider}"),
                key_hint="x",
                limit_usd=5.0,
                tracking_since=_NOW,
                created_at=_NOW,
            )
        )
    return repo


def test_lists_models_from_each_of_the_users_providers():
    cipher = FernetKeyCipher(Fernet.generate_key().decode())
    repo = _repo_with(cipher, "openai", "google")
    seen = {}

    def factory(provider, key):
        seen[provider] = key
        models = {
            "openai": [AvailableModel("gpt-4o", "OpenAI")],
            "google": [AvailableModel("gemini-2.0", "Google")],
        }[provider]
        return _StubProvider(models=models)

    provider = KeyedUserAvailableModelsProvider(repo, cipher, factory)

    models = {m.model for m in provider.list_models("u1")}

    assert models == {"gpt-4o", "gemini-2.0"}
    assert seen == {"openai": "key-openai", "google": "key-google"}


def test_a_user_with_no_keys_gets_no_models():
    cipher = FernetKeyCipher(Fernet.generate_key().decode())
    provider = KeyedUserAvailableModelsProvider(
        InMemoryApiKeyRepository(), cipher, lambda p, k: _StubProvider()
    )

    assert provider.list_models("u1") == []


def test_a_failing_provider_is_skipped_so_one_bad_key_doesnt_break_the_picker():
    cipher = FernetKeyCipher(Fernet.generate_key().decode())
    repo = _repo_with(cipher, "openai", "google")

    def factory(provider, key):
        if provider == "openai":
            return _StubProvider(error=RuntimeError("revoked"))
        return _StubProvider(models=[AvailableModel("gemini-2.0", "Google")])

    provider = KeyedUserAvailableModelsProvider(repo, cipher, factory)

    assert [m.model for m in provider.list_models("u1")] == ["gemini-2.0"]


def test_caching_serves_a_cached_list_per_user_within_ttl():
    now = [_NOW]
    inner_calls = {"u1": 0}

    class _Inner:
        def list_models(self, user_id):
            inner_calls[user_id] += 1
            return [AvailableModel("gpt-4o", "OpenAI")]

    caching = CachingUserAvailableModelsProvider(
        _Inner(), ttl_seconds=60, clock=lambda: now[0]
    )

    caching.list_models("u1")
    caching.list_models("u1")
    assert inner_calls["u1"] == 1  # second call served from cache

    now[0] = _NOW + timedelta(seconds=61)
    caching.list_models("u1")
    assert inner_calls["u1"] == 2  # cache expired


def test_caching_is_isolated_per_user():
    inner_calls = []

    class _Inner:
        def list_models(self, user_id):
            inner_calls.append(user_id)
            return []

    caching = CachingUserAvailableModelsProvider(_Inner(), ttl_seconds=60, clock=lambda: _NOW)

    caching.list_models("u1")
    caching.list_models("u2")

    assert inner_calls == ["u1", "u2"]


def test_invalidate_drops_a_users_cache_so_the_next_call_refetches():
    # A user's keys can change (add/delete) within the TTL; invalidate lets the picker
    # reflect the new key set immediately instead of waiting for the cache to expire.
    inner_calls = {"u1": 0}

    class _Inner:
        def list_models(self, user_id):
            inner_calls[user_id] += 1
            return [AvailableModel("gpt-4o", "OpenAI")]

    caching = CachingUserAvailableModelsProvider(_Inner(), ttl_seconds=300, clock=lambda: _NOW)

    caching.list_models("u1")
    caching.list_models("u1")
    assert inner_calls["u1"] == 1  # served from cache

    caching.invalidate("u1")
    caching.list_models("u1")
    assert inner_calls["u1"] == 2  # re-fetched after invalidation


def test_invalidate_an_uncached_user_is_harmless():
    caching = CachingUserAvailableModelsProvider(
        KeyedUserAvailableModelsProvider(
            InMemoryApiKeyRepository(),
            FernetKeyCipher(Fernet.generate_key().decode()),
            lambda p, k: _StubProvider(),
        ),
        ttl_seconds=300,
        clock=lambda: _NOW,
    )

    caching.invalidate("never-cached")  # must not raise

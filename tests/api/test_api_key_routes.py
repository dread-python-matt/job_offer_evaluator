from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.application.api_key_use_cases import (
    AddApiKeyUseCase,
    DeleteApiKeyUseCase,
    ListApiKeysUseCase,
    SetApiKeyBudgetUseCase,
)
from app.application.ports import ApiKeyValidator, UserProviderSpendProvider
from app.domain.auth import User
from app.domain.errors import InvalidApiKeyError
from app.infrastructure.fernet_key_cipher import FernetKeyCipher
from app.presentation.api.auth import get_current_user
from app.presentation.api.routes import (
    get_add_api_key_use_case,
    get_delete_api_key_use_case,
    get_list_api_keys_use_case,
    get_set_api_key_budget_use_case,
    router,
)
from tests.fakes import InMemoryApiKeyRepository


class _AcceptingValidator(ApiKeyValidator):
    def validate(self, provider, key):
        pass


class _RejectingValidator(ApiKeyValidator):
    def validate(self, provider, key):
        raise InvalidApiKeyError(provider)


class _FixedProviderSpend(UserProviderSpendProvider):
    def __init__(self, by_company=None):
        self._by_company = by_company or {}

    def spend_since(self, user_id, company, start):
        return self._by_company.get(company, 0.0)


def _build_client(
    repo=None, validator=None, spend=None
) -> tuple[TestClient, InMemoryApiKeyRepository]:
    repo = repo or InMemoryApiKeyRepository()
    cipher = FernetKeyCipher(Fernet.generate_key().decode())
    validator = validator or _AcceptingValidator()
    spend = spend or _FixedProviderSpend()

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: User(
        id="user-1", email="dev@example.com", password_hash="x"
    )
    app.dependency_overrides[get_add_api_key_use_case] = lambda: AddApiKeyUseCase(
        repo, cipher, validator
    )
    app.dependency_overrides[get_list_api_keys_use_case] = lambda: ListApiKeysUseCase(repo, spend)
    app.dependency_overrides[get_set_api_key_budget_use_case] = lambda: SetApiKeyBudgetUseCase(
        repo, spend
    )
    app.dependency_overrides[get_delete_api_key_use_case] = lambda: DeleteApiKeyUseCase(repo)
    return TestClient(app), repo


def test_post_api_key_stores_and_returns_masked_view():
    client, repo = _build_client()

    response = client.post(
        "/api-keys",
        json={"api_provider": "openai", "key": "sk-secret-value-1234", "limit_usd": 10.0},
    )

    assert response.status_code == 201
    body = response.json()
    assert body == {
        "api_provider": "openai",
        "key_hint": "sk-…1234",
        "limit_usd": 10.0,
        "used_usd": 0.0,
    }
    # The plaintext key is never echoed back.
    assert "sk-secret-value-1234" not in response.text
    assert repo.get("user-1", "openai") is not None


def test_post_api_key_rejected_by_provider_returns_400():
    client, repo = _build_client(validator=_RejectingValidator())

    response = client.post(
        "/api-keys",
        json={"api_provider": "openai", "key": "sk-bad", "limit_usd": 5.0},
    )

    assert response.status_code == 400
    assert repo.get("user-1", "openai") is None


def test_post_api_key_unsupported_provider_returns_400():
    client, _ = _build_client()

    response = client.post(
        "/api-keys",
        json={"api_provider": "anthropic", "key": "sk-x", "limit_usd": 5.0},
    )

    assert response.status_code == 400


def test_post_duplicate_provider_returns_409():
    client, _ = _build_client()
    client.post(
        "/api-keys", json={"api_provider": "openai", "key": "sk-one-1234", "limit_usd": 5.0}
    )

    response = client.post(
        "/api-keys", json={"api_provider": "openai", "key": "sk-two-5678", "limit_usd": 5.0}
    )

    assert response.status_code == 409


def test_get_api_keys_lists_with_derived_usage():
    client, _ = _build_client(spend=_FixedProviderSpend({"OpenAI": 4.0}))
    client.post(
        "/api-keys", json={"api_provider": "openai", "key": "sk-openai-key-1234", "limit_usd": 10.0}
    )

    response = client.get("/api-keys")

    assert response.status_code == 200
    [item] = response.json()
    assert item == {
        "api_provider": "openai",
        "key_hint": "sk-…1234",
        "limit_usd": 10.0,
        "used_usd": 4.0,
    }


def test_patch_api_key_budget_updates_limit():
    client, repo = _build_client()
    client.post(
        "/api-keys", json={"api_provider": "openai", "key": "sk-openai-key-1234", "limit_usd": 10.0}
    )

    response = client.patch("/api-keys/openai", json={"limit_usd": 30.0})

    assert response.status_code == 200
    assert response.json()["limit_usd"] == 30.0
    assert repo.get("user-1", "openai").limit_usd == 30.0


def test_patch_missing_api_key_returns_404():
    client, _ = _build_client()

    response = client.patch("/api-keys/openai", json={"limit_usd": 30.0})

    assert response.status_code == 404


def test_delete_api_key_removes_it():
    client, repo = _build_client()
    client.post(
        "/api-keys", json={"api_provider": "openai", "key": "sk-openai-key-1234", "limit_usd": 10.0}
    )

    response = client.delete("/api-keys/openai")

    assert response.status_code == 204
    assert repo.get("user-1", "openai") is None


def test_delete_missing_api_key_returns_404():
    client, _ = _build_client()

    response = client.delete("/api-keys/openai")

    assert response.status_code == 404


def test_get_providers_lists_supported_providers():
    client, _ = _build_client()

    response = client.get("/api-keys/providers")

    assert response.status_code == 200
    providers = {p["provider"]: p["company"] for p in response.json()}
    assert providers == {"openai": "OpenAI", "google": "Google"}

from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.application.admin_key_use_cases import (
    DeleteAdminKeyUseCase,
    GetAdminKeyUseCase,
    SetAdminKeyUseCase,
)
from app.domain.auth import User
from app.infrastructure.fernet_key_cipher import FernetKeyCipher
from app.presentation.api.auth import get_current_user
from app.presentation.api.routes import (
    get_admin_key_use_case,
    get_delete_admin_key_use_case,
    get_set_admin_key_use_case,
    router,
)
from tests.fakes import FakeAdminKeyValidator, InMemoryAdminKeyRepository


def _build_client(repo=None, validator=None) -> tuple[TestClient, InMemoryAdminKeyRepository]:
    repo = repo or InMemoryAdminKeyRepository()
    cipher = FernetKeyCipher(Fernet.generate_key().decode())
    validator = validator or FakeAdminKeyValidator()

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: User(
        id="user-1", email="dev@example.com", password_hash="x"
    )
    app.dependency_overrides[get_admin_key_use_case] = lambda: GetAdminKeyUseCase(repo)
    app.dependency_overrides[get_set_admin_key_use_case] = lambda: SetAdminKeyUseCase(
        repo, cipher, validator
    )
    app.dependency_overrides[get_delete_admin_key_use_case] = lambda: DeleteAdminKeyUseCase(repo)
    return TestClient(app), repo


def test_get_admin_key_returns_null_when_none_is_saved():
    client, _ = _build_client()

    response = client.get("/admin-key")

    assert response.status_code == 200
    assert response.json() is None


def test_put_admin_key_stores_and_returns_masked_view():
    client, repo = _build_client()

    response = client.put("/admin-key", json={"key": "sk-admin-secret-1234"})

    assert response.status_code == 200
    assert response.json()["key_hint"] == "sk-…1234"
    # The plaintext key is never echoed back, and only ciphertext is stored.
    assert "sk-admin-secret-1234" not in response.text
    assert repo.get("user-1") is not None


def test_get_admin_key_returns_the_masked_hint_after_it_is_saved():
    client, _ = _build_client()
    client.put("/admin-key", json={"key": "sk-admin-secret-1234"})

    response = client.get("/admin-key")

    assert response.status_code == 200
    assert response.json()["key_hint"] == "sk-…1234"


def test_put_admin_key_rejected_by_provider_returns_400():
    client, repo = _build_client(validator=FakeAdminKeyValidator(reject={"sk-bad"}))

    response = client.put("/admin-key", json={"key": "sk-bad"})

    assert response.status_code == 400
    assert repo.get("user-1") is None


def test_delete_admin_key_removes_it_and_is_idempotent():
    client, repo = _build_client()
    client.put("/admin-key", json={"key": "sk-admin-secret-1234"})

    first = client.delete("/admin-key")
    second = client.delete("/admin-key")  # already gone

    assert first.status_code == 204
    assert second.status_code == 204
    assert repo.get("user-1") is None

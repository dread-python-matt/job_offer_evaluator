from app.application.ports import ApiKeyRepository, KeyCipher
from app.domain.errors import MissingProviderApiKeyError


class UserApiKeyResolver:
    """Resolves a user's plaintext provider API key on demand for the scoring path:
    looks up the stored key for a provider and decrypts it. Raises
    `MissingProviderApiKeyError` when the user has no key for that provider (require
    own key — there is no shared/env fallback)."""

    def __init__(self, repository: ApiKeyRepository, cipher: KeyCipher) -> None:
        self._repository = repository
        self._cipher = cipher

    def key_for_provider(self, user_id: str, api_provider: str) -> str:
        record = self._repository.get(user_id, api_provider)
        if record is None:
            raise MissingProviderApiKeyError(api_provider)
        return self._cipher.decrypt(record.key_ciphertext)

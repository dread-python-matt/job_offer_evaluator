from app.application.ports import AdminKeyRepository, KeyCipher


class AdminKeyResolver:
    """Resolves a user's plaintext OpenAI admin key on demand for the org-spend/usage
    readouts: looks up the stored key and decrypts it. Returns None when the user has no
    admin key, so callers can fall back to the env admin key (or report 'unavailable')."""

    def __init__(self, repository: AdminKeyRepository, cipher: KeyCipher) -> None:
        self._repository = repository
        self._cipher = cipher

    def key_for_user(self, user_id: str) -> str | None:
        record = self._repository.get(user_id)
        if record is None:
            return None
        return self._cipher.decrypt(record.key_ciphertext)

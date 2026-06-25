from collections.abc import Callable

from app.application.ports import ApiKeyValidator, AvailableModelsProvider
from app.domain.errors import InvalidApiKeyError

# HTTP statuses a provider returns when the key itself is the problem (bad/revoked key,
# or a key without the needed scope). Anything else is treated as transient and bubbles.
_KEY_REJECTION_STATUSES = frozenset({401, 403})

ProviderFactory = Callable[[str, str], AvailableModelsProvider]


class ModelListingApiKeyValidator(ApiKeyValidator):
    """Validates a key by listing the provider's models with it. The list-models call is
    free (no tokens billed) and reuses the existing per-provider model-list providers,
    built on demand by `provider_factory` so this stays unit-testable without the network."""

    def __init__(self, provider_factory: ProviderFactory) -> None:
        self._provider_factory = provider_factory

    def validate(self, provider: str, key: str) -> None:
        models_provider = self._provider_factory(provider, key)
        try:
            models_provider.list_models()
        except Exception as exc:
            if getattr(exc, "status_code", None) in _KEY_REJECTION_STATUSES:
                raise InvalidApiKeyError(provider) from exc
            raise

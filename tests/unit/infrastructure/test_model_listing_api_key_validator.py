import pytest

from app.application.ports import AvailableModel, AvailableModelsProvider
from app.domain.errors import InvalidApiKeyError
from app.infrastructure.model_listing_api_key_validator import ModelListingApiKeyValidator


class _StubProvider(AvailableModelsProvider):
    def __init__(self, models=None, error=None):
        self._models = models or []
        self._error = error

    def list_models(self):
        if self._error is not None:
            raise self._error
        return self._models


class _StatusError(Exception):
    """Stands in for an OpenAI SDK APIStatusError, which carries an HTTP status_code."""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"status {status_code}")
        self.status_code = status_code


def _validator(provider_for):
    return ModelListingApiKeyValidator(provider_factory=lambda p, k: provider_for(p, k))


def test_validate_passes_when_the_provider_lists_models():
    validator = _validator(lambda p, k: _StubProvider(models=[AvailableModel("gpt-4o", "OpenAI")]))

    validator.validate("openai", "sk-good")  # does not raise


def test_validate_rejects_a_key_the_provider_returns_401_for():
    validator = _validator(lambda p, k: _StubProvider(error=_StatusError(401)))

    with pytest.raises(InvalidApiKeyError):
        validator.validate("openai", "sk-bad")


def test_validate_rejects_a_key_the_provider_returns_403_for():
    validator = _validator(lambda p, k: _StubProvider(error=_StatusError(403)))

    with pytest.raises(InvalidApiKeyError):
        validator.validate("openai", "sk-bad")


def test_validate_rejects_a_key_the_provider_returns_400_for():
    # Gemini returns 400 ("Please pass a valid API key") for a bad key, not 401/403.
    validator = _validator(lambda p, k: _StubProvider(error=_StatusError(400)))

    with pytest.raises(InvalidApiKeyError):
        validator.validate("google", "AIza-bad")


def test_validate_does_not_swallow_a_transient_provider_error():
    # A 500 (or any non-auth failure) must not be misreported as an invalid key.
    validator = _validator(lambda p, k: _StubProvider(error=_StatusError(500)))

    with pytest.raises(_StatusError):
        validator.validate("openai", "sk-maybe-good")


def test_validate_passes_the_provider_and_key_to_the_factory():
    seen = {}

    def factory(provider, key):
        seen["provider"] = provider
        seen["key"] = key
        return _StubProvider(models=[])

    ModelListingApiKeyValidator(provider_factory=factory).validate("google", "AIza-key")

    assert seen == {"provider": "google", "key": "AIza-key"}

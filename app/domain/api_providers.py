"""The set of LLM API providers a user may register their own key for.

`api_provider` is the canonical lowercase identifier stored against a key and chosen by
the user from a fixed list. `company` is the existing label used elsewhere (model usage,
available models) — the two are mapped here so per-provider budget accounting lines up."""

from app.domain.errors import UnsupportedApiProviderError

# Canonical provider id -> the `company` label used by model usage / available models.
_PROVIDER_COMPANY: dict[str, str] = {
    "openai": "OpenAI",
    "google": "Google",
}

SUPPORTED_API_PROVIDERS: tuple[str, ...] = tuple(_PROVIDER_COMPANY)


def is_supported_provider(provider: str) -> bool:
    return provider in _PROVIDER_COMPANY


def company_for_provider(provider: str) -> str:
    """The `company` label for a provider id. Raises UnsupportedApiProviderError for an
    unknown provider, so callers never silently mis-attribute usage."""
    try:
        return _PROVIDER_COMPANY[provider]
    except KeyError as exc:
        raise UnsupportedApiProviderError(provider) from exc

from abc import ABC, abstractmethod

from app.application.ports import ExternalUsageProvider
from app.infrastructure.no_external_usage_provider import NoExternalUsageProvider


class LLMProviderFactory(ABC):
    """Encapsulates all LLM-provider-specific wiring so that main.py branches only
    once (to pick a factory) rather than branching on provider throughout setup."""

    @abstractmethod
    def configure_sdk(self) -> None: ...

    @abstractmethod
    def build_external_usage_provider(self) -> ExternalUsageProvider: ...


class OpenAIProviderFactory(LLMProviderFactory):
    def __init__(self, api_key: str, admin_key: str | None = None) -> None:
        self._api_key = api_key
        self._admin_key = admin_key

    def configure_sdk(self) -> None:
        from app.infrastructure.openai_client import configure_openai
        configure_openai(self._api_key)

    def build_external_usage_provider(self) -> ExternalUsageProvider:
        if self._admin_key:
            from openai import OpenAI
            from app.infrastructure.openai_usage_provider import OpenAIExternalUsageProvider
            return OpenAIExternalUsageProvider(OpenAI(api_key=self._admin_key))
        return NoExternalUsageProvider()


class GeminiProviderFactory(LLMProviderFactory):
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def configure_sdk(self) -> None:
        from app.infrastructure.gemini_client import configure_gemini
        configure_gemini(self._api_key)

    def build_external_usage_provider(self) -> ExternalUsageProvider:
        return NoExternalUsageProvider()


def build_llm_provider_factory(
    provider: str,
    openai_api_key: str | None,
    openai_admin_key: str | None,
    gemini_api_key: str | None,
) -> LLMProviderFactory:
    if provider == "openai":
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY must be set in .env when LLM_PROVIDER=openai")
        return OpenAIProviderFactory(openai_api_key, openai_admin_key)
    if provider == "gemini":
        if not gemini_api_key:
            raise ValueError("GEMINI_API_KEY must be set in .env when LLM_PROVIDER=gemini")
        return GeminiProviderFactory(gemini_api_key)
    raise ValueError(f"Unknown LLM_PROVIDER={provider!r}. Supported values: 'gemini', 'openai'")

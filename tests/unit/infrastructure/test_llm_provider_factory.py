from app.infrastructure.llm_provider_factory import (
    GeminiProviderFactory,
    OpenAIProviderFactory,
    build_llm_provider_factory,
)
from app.infrastructure.openai_spend_provider import OpenAISpendProvider
from app.infrastructure.openai_usage_provider import OpenAIExternalUsageProvider


def test_gemini_factory_has_no_spend_provider():
    factory = GeminiProviderFactory("gemini-key")

    assert factory.build_spend_provider() is None


def test_gemini_factory_has_no_external_usage_provider():
    factory = GeminiProviderFactory("gemini-key")

    assert factory.build_external_usage_provider() is None


def test_openai_factory_builds_external_usage_provider_with_admin_key():
    factory = OpenAIProviderFactory("api-key", admin_key="admin-key")

    assert isinstance(factory.build_external_usage_provider(), OpenAIExternalUsageProvider)


def test_openai_factory_has_no_external_usage_provider_without_admin_key():
    factory = OpenAIProviderFactory("api-key", admin_key=None)

    assert factory.build_external_usage_provider() is None


def test_openai_factory_builds_spend_provider_with_admin_key():
    factory = OpenAIProviderFactory("api-key", admin_key="admin-key")

    assert isinstance(factory.build_spend_provider(), OpenAISpendProvider)


def test_openai_factory_has_no_spend_provider_without_admin_key():
    factory = OpenAIProviderFactory("api-key", admin_key=None)

    assert factory.build_spend_provider() is None


def test_build_factory_for_gemini_never_gates_on_openai_spend():
    factory = build_llm_provider_factory(
        "gemini",
        openai_api_key="api-key",
        openai_admin_key="admin-key",
        gemini_api_key="gemini-key",
    )

    assert factory.build_spend_provider() is None


def test_build_factory_for_openai_builds_spend_provider():
    factory = build_llm_provider_factory(
        "openai",
        openai_api_key="api-key",
        openai_admin_key="admin-key",
        gemini_api_key="",
    )

    assert isinstance(factory.build_spend_provider(), OpenAISpendProvider)

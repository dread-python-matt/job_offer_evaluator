from unittest.mock import patch

import pytest

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

    assert isinstance(
        factory.build_external_usage_provider(), OpenAIExternalUsageProvider
    )


def test_openai_factory_builds_usage_provider_authenticating_with_admin_api_key():
    # Regression: org usage routes require `admin_api_key`. Building the client with `api_key`
    # makes the SDK raise a TypeError on these routes, so the org-usage readout never works.
    factory = OpenAIProviderFactory("api-key", admin_key="admin-key")

    with patch("openai.OpenAI") as mock_cls:
        factory.build_external_usage_provider()

    assert mock_cls.call_args.kwargs.get("admin_api_key") == "admin-key"
    assert "api_key" not in mock_cls.call_args.kwargs


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


def test_build_factory_boots_without_any_gemini_key():
    # Scoring uses each user's own key; the env key is optional. A missing key must not block
    # startup — the org-level providers just degrade to None.
    factory = build_llm_provider_factory(
        "gemini", openai_api_key="", openai_admin_key="", gemini_api_key=""
    )

    assert isinstance(factory, GeminiProviderFactory)
    assert factory.build_spend_provider() is None
    assert factory.build_external_usage_provider() is None


def test_build_factory_boots_without_any_openai_key():
    factory = build_llm_provider_factory(
        "openai", openai_api_key="", openai_admin_key="", gemini_api_key=""
    )

    assert isinstance(factory, OpenAIProviderFactory)
    assert factory.build_spend_provider() is None
    assert factory.build_external_usage_provider() is None


def test_build_factory_rejects_unknown_provider():
    with pytest.raises(ValueError, match="Unknown LLM_PROVIDER"):
        build_llm_provider_factory(
            "anthropic", openai_api_key="k", openai_admin_key="", gemini_api_key="k"
        )

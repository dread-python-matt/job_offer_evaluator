from types import SimpleNamespace
from unittest.mock import patch

from app.infrastructure.openai_available_models_provider import OpenAIAvailableModelsProvider
from app.infrastructure.gemini_available_models_provider import GeminiAvailableModelsProvider


def _model(id: str):
    return SimpleNamespace(id=id)


# --- OpenAI provider ---

def test_openai_provider_returns_structured_output_capable_models_only():
    with patch("app.infrastructure.openai_available_models_provider.OpenAI") as mock_cls:
        mock_cls.return_value.models.list.return_value = [
            _model("gpt-4o"),
            _model("gpt-4o-mini"),
            _model("gpt-4.1"),
            _model("gpt-4.1-mini"),
            _model("o1"),
            _model("o3-mini"),
            _model("o4-mini"),
            _model("text-embedding-ada-002"),
            _model("whisper-1"),
            _model("dall-e-3"),
        ]
        provider = OpenAIAvailableModelsProvider(api_key="test-key")
        models = provider.list_models()

    ids = [m.model for m in models]
    assert "gpt-4o" in ids
    assert "gpt-4o-mini" in ids
    assert "gpt-4.1" in ids
    assert "gpt-4.1-mini" in ids
    assert "o1" in ids
    assert "o3-mini" in ids
    assert "o4-mini" in ids
    assert "text-embedding-ada-002" not in ids
    assert "whisper-1" not in ids
    assert "dall-e-3" not in ids


def test_openai_provider_excludes_models_without_structured_outputs():
    """Models that reject response_format=json_schema (HTTP 400 from the scoring
    agent) must not be advertised: legacy chat models, instruct/non-text variants,
    o1-mini/preview, and the pre-structured-outputs gpt-4o snapshot."""
    with patch("app.infrastructure.openai_available_models_provider.OpenAI") as mock_cls:
        mock_cls.return_value.models.list.return_value = [
            _model("gpt-3.5-turbo"),
            _model("gpt-3.5-turbo-instruct"),
            _model("gpt-4"),
            _model("gpt-4-0613"),
            _model("gpt-4-turbo"),
            _model("gpt-4o-2024-05-13"),
            _model("gpt-4o-audio-preview"),
            _model("gpt-4o-realtime-preview"),
            _model("gpt-4o-transcribe"),
            _model("gpt-4o-mini-tts"),
            _model("gpt-4o-search-preview"),
            _model("o1-mini"),
            _model("o1-preview"),
            _model("gpt-4o"),
        ]
        provider = OpenAIAvailableModelsProvider(api_key="test-key")
        models = provider.list_models()

    assert [m.model for m in models] == ["gpt-4o"]


def test_openai_provider_tags_company_as_openai():
    with patch("app.infrastructure.openai_available_models_provider.OpenAI") as mock_cls:
        mock_cls.return_value.models.list.return_value = [_model("gpt-4o")]
        provider = OpenAIAvailableModelsProvider(api_key="test-key")
        models = provider.list_models()

    assert all(m.company == "OpenAI" for m in models)


def test_openai_provider_returns_sorted_models():
    with patch("app.infrastructure.openai_available_models_provider.OpenAI") as mock_cls:
        mock_cls.return_value.models.list.return_value = [
            _model("gpt-4o-mini"),
            _model("gpt-4o"),
            _model("o1-mini"),
        ]
        provider = OpenAIAvailableModelsProvider(api_key="test-key")
        models = provider.list_models()

    assert [m.model for m in models] == sorted(m.model for m in models)


# --- Gemini provider ---

def test_gemini_provider_returns_gemini_models_only():
    with patch("app.infrastructure.gemini_available_models_provider.OpenAI") as mock_cls:
        mock_cls.return_value.models.list.return_value = [
            _model("gemini-2.0-flash"),
            _model("gemini-1.5-pro"),
            _model("text-embedding-004"),
            _model("embedding-001"),
        ]
        provider = GeminiAvailableModelsProvider(api_key="test-key")
        models = provider.list_models()

    ids = [m.model for m in models]
    assert "gemini-2.0-flash" in ids
    assert "gemini-1.5-pro" in ids
    assert "text-embedding-004" not in ids
    assert "embedding-001" not in ids


def test_gemini_provider_excludes_non_text_generation_models():
    """Embedding / image / TTS / audio / live / computer-use / robotics models can't back the
    chat + json_schema scorer, so they must not be advertised even though their ids start with
    'gemini-'. (Ids taken from a real 2026 API listing.)"""
    with patch("app.infrastructure.gemini_available_models_provider.OpenAI") as mock_cls:
        mock_cls.return_value.models.list.return_value = [
            _model("gemini-2.5-flash"),
            _model("gemini-3.5-flash"),
            _model("gemini-flash-latest"),
            _model("gemini-embedding-001"),
            _model("gemini-2.5-flash-image"),
            _model("gemini-2.5-flash-preview-tts"),
            _model("gemini-2.5-flash-native-audio-latest"),
            _model("gemini-3.1-flash-live-preview"),
            _model("gemini-2.5-computer-use-preview-10-2025"),
            _model("gemini-robotics-er-1.6-preview"),
        ]
        provider = GeminiAvailableModelsProvider(api_key="test-key")
        models = provider.list_models()

    assert [m.model for m in models] == [
        "gemini-2.5-flash",
        "gemini-3.5-flash",
        "gemini-flash-latest",
    ]


def test_gemini_provider_still_lists_text_models_it_cannot_know_are_quota_limited():
    # The picker filters by capability, not account-specific quota: a text model retired from
    # the free tier (gemini-2.0-flash-lite -> limit:0) is still a text model, so it stays listed
    # and the scorer surfaces the quota error. Documents the deliberate boundary.
    with patch("app.infrastructure.gemini_available_models_provider.OpenAI") as mock_cls:
        mock_cls.return_value.models.list.return_value = [_model("gemini-2.0-flash-lite")]
        provider = GeminiAvailableModelsProvider(api_key="test-key")
        models = provider.list_models()

    assert [m.model for m in models] == ["gemini-2.0-flash-lite"]


def test_gemini_provider_strips_models_prefix_from_id():
    with patch("app.infrastructure.gemini_available_models_provider.OpenAI") as mock_cls:
        mock_cls.return_value.models.list.return_value = [
            _model("models/gemini-2.0-flash"),
        ]
        provider = GeminiAvailableModelsProvider(api_key="test-key")
        models = provider.list_models()

    assert models[0].model == "gemini-2.0-flash"


def test_gemini_provider_tags_company_as_google():
    with patch("app.infrastructure.gemini_available_models_provider.OpenAI") as mock_cls:
        mock_cls.return_value.models.list.return_value = [_model("gemini-2.0-flash")]
        provider = GeminiAvailableModelsProvider(api_key="test-key")
        models = provider.list_models()

    assert all(m.company == "Google" for m in models)


def test_gemini_provider_returns_sorted_models():
    with patch("app.infrastructure.gemini_available_models_provider.OpenAI") as mock_cls:
        mock_cls.return_value.models.list.return_value = [
            _model("gemini-2.0-flash"),
            _model("gemini-1.5-pro"),
            _model("gemini-1.5-flash"),
        ]
        provider = GeminiAvailableModelsProvider(api_key="test-key")
        models = provider.list_models()

    assert [m.model for m in models] == sorted(m.model for m in models)

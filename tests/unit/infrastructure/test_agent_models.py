from unittest.mock import patch

from app.infrastructure.agent_models import build_chat_model, build_chat_model_with_key


def test_gemini_model_gets_a_client_on_the_gemini_endpoint():
    with (
        patch("app.infrastructure.agent_models.AsyncOpenAI") as client_cls,
        patch("app.infrastructure.agent_models.OpenAIChatCompletionsModel") as model_cls,
    ):
        build_chat_model("gemini-2.5-flash", openai_api_key="o", gemini_api_key="g", timeout=30)

    kwargs = client_cls.call_args.kwargs
    assert kwargs["api_key"] == "g"
    assert "generativelanguage" in kwargs["base_url"]
    assert kwargs["timeout"] == 30
    assert model_cls.call_args.kwargs["model"] == "gemini-2.5-flash"
    assert model_cls.call_args.kwargs["openai_client"] is client_cls.return_value


def test_openai_model_gets_a_default_endpoint_client():
    with (
        patch("app.infrastructure.agent_models.AsyncOpenAI") as client_cls,
        patch("app.infrastructure.agent_models.OpenAIChatCompletionsModel"),
    ):
        build_chat_model("gpt-4o", openai_api_key="o", gemini_api_key="g")

    kwargs = client_cls.call_args.kwargs
    assert kwargs["api_key"] == "o"
    assert "base_url" not in kwargs  # standard OpenAI endpoint


def test_with_key_routes_a_gemini_model_to_the_gemini_endpoint():
    with (
        patch("app.infrastructure.agent_models.AsyncOpenAI") as client_cls,
        patch("app.infrastructure.agent_models.OpenAIChatCompletionsModel"),
    ):
        build_chat_model_with_key("gemini-2.5-flash", api_key="user-key", timeout=30)

    kwargs = client_cls.call_args.kwargs
    assert kwargs["api_key"] == "user-key"
    assert "generativelanguage" in kwargs["base_url"]


def test_with_key_routes_an_openai_model_to_the_default_endpoint():
    with (
        patch("app.infrastructure.agent_models.AsyncOpenAI") as client_cls,
        patch("app.infrastructure.agent_models.OpenAIChatCompletionsModel"),
    ):
        build_chat_model_with_key("gpt-4o", api_key="user-key")

    kwargs = client_cls.call_args.kwargs
    assert kwargs["api_key"] == "user-key"
    assert "base_url" not in kwargs

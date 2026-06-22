from unittest.mock import patch

from app.infrastructure.gemini_client import GEMINI_BASE_URL, configure_gemini


def test_configure_gemini_points_the_default_client_at_the_gemini_endpoint():
    with (
        patch("app.infrastructure.gemini_client.set_default_openai_client") as set_client,
        patch("app.infrastructure.gemini_client.set_default_openai_api") as set_api,
        patch("app.infrastructure.gemini_client.set_tracing_disabled") as set_tracing,
    ):
        configure_gemini("fake-key")

    client = set_client.call_args.args[0]
    assert client.api_key == "fake-key"
    assert str(client.base_url) == GEMINI_BASE_URL
    set_api.assert_called_once_with("chat_completions")
    set_tracing.assert_called_once_with(True)

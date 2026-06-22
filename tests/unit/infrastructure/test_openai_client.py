from unittest.mock import patch

from app.infrastructure.openai_client import configure_openai


def test_configure_openai_sets_the_openai_client_with_the_given_key():
    with (
        patch("app.infrastructure.openai_client.set_default_openai_client") as set_client,
        patch("app.infrastructure.openai_client.set_default_openai_api"),
        patch("app.infrastructure.openai_client.set_tracing_disabled"),
    ):
        configure_openai("sk-fake-key")

    client = set_client.call_args.args[0]
    assert client.api_key == "sk-fake-key"


def test_configure_openai_uses_chat_completions_api():
    with (
        patch("app.infrastructure.openai_client.set_default_openai_client"),
        patch("app.infrastructure.openai_client.set_default_openai_api") as set_api,
        patch("app.infrastructure.openai_client.set_tracing_disabled"),
    ):
        configure_openai("sk-fake-key")

    set_api.assert_called_once_with("chat_completions")


def test_configure_openai_disables_tracing():
    with (
        patch("app.infrastructure.openai_client.set_default_openai_client"),
        patch("app.infrastructure.openai_client.set_default_openai_api"),
        patch("app.infrastructure.openai_client.set_tracing_disabled") as set_tracing,
    ):
        configure_openai("sk-fake-key")

    set_tracing.assert_called_once_with(True)

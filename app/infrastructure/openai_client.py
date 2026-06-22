from agents import set_default_openai_api, set_default_openai_client, set_tracing_disabled
from openai import AsyncOpenAI


def configure_openai(api_key: str) -> None:
    """Point the Agents SDK's default client at OpenAI's standard endpoint.

    Uses the chat_completions API (consistent with the Gemini adapter) and disables
    tracing, since there is no guaranteed tracing backend configured.
    """
    set_default_openai_client(AsyncOpenAI(api_key=api_key))
    set_default_openai_api("chat_completions")
    set_tracing_disabled(True)

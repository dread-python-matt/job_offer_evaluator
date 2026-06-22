from agents import set_default_openai_api, set_default_openai_client, set_tracing_disabled
from openai import AsyncOpenAI

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


def configure_gemini(api_key: str) -> None:
    """Point the Agents SDK's default OpenAI client at Gemini's OpenAI-compatible endpoint.

    Gemini's compatibility layer only implements the chat completions API, not OpenAI's
    Responses API, and has no tracing backend, so both are switched accordingly.
    """
    set_default_openai_client(AsyncOpenAI(api_key=api_key, base_url=GEMINI_BASE_URL))
    set_default_openai_api("chat_completions")
    set_tracing_disabled(True)

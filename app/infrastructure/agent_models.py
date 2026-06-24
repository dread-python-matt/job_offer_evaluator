from agents import OpenAIChatCompletionsModel
from openai import AsyncOpenAI

from app.infrastructure.gemini_client import GEMINI_BASE_URL
from app.infrastructure.llm_utils import company_from_model


def build_chat_model(
    model_name: str,
    *,
    openai_api_key: str,
    gemini_api_key: str,
    timeout: float = 60.0,
) -> OpenAIChatCompletionsModel:
    """Build a chat model bound to its own client, routed to the right provider by the
    model name. Because each agent carries its own client, switching the active model
    never mutates global SDK state — so concurrent matches on different models stay
    isolated (the H1 fix)."""
    if company_from_model(model_name) == "Google":
        client = AsyncOpenAI(api_key=gemini_api_key, base_url=GEMINI_BASE_URL, timeout=timeout)
    else:
        client = AsyncOpenAI(api_key=openai_api_key, timeout=timeout)
    return OpenAIChatCompletionsModel(model=model_name, openai_client=client)

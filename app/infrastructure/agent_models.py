from agents import OpenAIChatCompletionsModel
from openai import AsyncOpenAI

from app.infrastructure.gemini_client import GEMINI_BASE_URL
from app.infrastructure.llm_utils import company_from_model


def build_chat_model_with_key(
    model_name: str,
    *,
    api_key: str,
    timeout: float = 60.0,
) -> OpenAIChatCompletionsModel:
    """Build a chat model bound to its own client using a single API key, routed to the
    right provider endpoint by the model name. Used for per-user scoring, where the key is
    the calling user's own provider key. Each agent carries its own client, so concurrent
    matches across users/models stay isolated and never mutate global SDK state."""
    if company_from_model(model_name) == "Google":
        client = AsyncOpenAI(api_key=api_key, base_url=GEMINI_BASE_URL, timeout=timeout)
    else:
        client = AsyncOpenAI(api_key=api_key, timeout=timeout)
    return OpenAIChatCompletionsModel(model=model_name, openai_client=client)


def build_chat_model(
    model_name: str,
    *,
    openai_api_key: str,
    gemini_api_key: str,
    timeout: float = 60.0,
) -> OpenAIChatCompletionsModel:
    """Build a chat model from a pair of provider keys, picking the one for the model's
    provider. (The per-user scoring path uses `build_chat_model_with_key` instead.)"""
    key = gemini_api_key if company_from_model(model_name) == "Google" else openai_api_key
    return build_chat_model_with_key(model_name, api_key=key, timeout=timeout)

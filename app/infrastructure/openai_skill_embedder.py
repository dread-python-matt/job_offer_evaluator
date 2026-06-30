"""OpenAI embeddings adapter for the (offline) alias suggester — not used in the request path.

The SDK client is injected so the adapter can be unit-tested without a network call; `create()`
builds a real client from an API key, mirroring the chat adapters' construction convention.
"""

from typing import Any

from app.domain.skills import SkillEmbedder

_DEFAULT_MODEL = "text-embedding-3-small"


class OpenAISkillEmbedder(SkillEmbedder):
    def __init__(self, client: Any, model: str = _DEFAULT_MODEL) -> None:
        self._client = client
        self._model = model

    @classmethod
    def create(
        cls, api_key: str, *, model: str = _DEFAULT_MODEL, timeout: float = 60.0
    ) -> "OpenAISkillEmbedder":
        from openai import OpenAI

        return cls(OpenAI(api_key=api_key, timeout=timeout), model=model)

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self._client.embeddings.create(model=self._model, input=list(texts))
        return [item.embedding for item in response.data]

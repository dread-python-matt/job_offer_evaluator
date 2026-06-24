from openai import OpenAI

from app.application.ports import AvailableModel, AvailableModelsProvider
from app.infrastructure.gemini_client import GEMINI_BASE_URL


class GeminiAvailableModelsProvider(AvailableModelsProvider):
    def __init__(self, api_key: str, timeout: float = 60.0) -> None:
        self._api_key = api_key
        self._timeout = timeout

    def list_models(self) -> list[AvailableModel]:
        client = OpenAI(api_key=self._api_key, base_url=GEMINI_BASE_URL, timeout=self._timeout)
        models = []
        for m in client.models.list():
            model_id = m.id.removeprefix("models/")
            if model_id.startswith("gemini-"):
                models.append(AvailableModel(model=model_id, company="Google"))
        return sorted(models, key=lambda m: m.model)

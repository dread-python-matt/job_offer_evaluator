from openai import OpenAI

from app.application.ports import AvailableModel, AvailableModelsProvider
from app.infrastructure.gemini_client import GEMINI_BASE_URL

# Gemini's model list mixes general text models with ones that can't back the chat + json_schema
# scorer: embeddings, image / audio / TTS generation, live (bidi-streaming) endpoints, computer-use,
# and robotics. Advertise only text-generation models so a user can't pick one that always fails.
# This can't know account-specific quota — a text model retired from the free tier (e.g.
# gemini-2.0-flash-lite returning `limit: 0`) is still a text model, so it stays listed and the
# scorer surfaces that as a fail-fast quota error instead.
_NON_TEXT_MARKERS = (
    "embedding",     # gemini-embedding-* — vector embeddings, not chat
    "image",         # *-flash-image / *-pro-image — image generation
    "tts",           # *-preview-tts — text-to-speech
    "audio",         # *-native-audio-* — speech I/O
    "live",          # *-live-* / *-live-translate-* — realtime bidi, not chat completions
    "computer-use",  # *-computer-use-* — computer-control agent
    "robotics",      # gemini-robotics-* — robotics
)


def _is_text_generation_model(model_id: str) -> bool:
    return model_id.startswith("gemini-") and not any(m in model_id for m in _NON_TEXT_MARKERS)


class GeminiAvailableModelsProvider(AvailableModelsProvider):
    def __init__(self, api_key: str, timeout: float = 60.0) -> None:
        self._api_key = api_key
        self._timeout = timeout

    def list_models(self) -> list[AvailableModel]:
        client = OpenAI(api_key=self._api_key, base_url=GEMINI_BASE_URL, timeout=self._timeout)
        models = [
            AvailableModel(model=model_id, company="Google")
            for model_id in (m.id.removeprefix("models/") for m in client.models.list())
            if _is_text_generation_model(model_id)
        ]
        return sorted(models, key=lambda m: m.model)

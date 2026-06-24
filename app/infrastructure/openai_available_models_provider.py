from openai import OpenAI

from app.application.ports import AvailableModel, AvailableModelsProvider

# The scoring agent runs with a structured (json_schema) output type, and OpenAI
# returns HTTP 400 for response_format=json_schema on any model that doesn't support
# Structured Outputs. So we advertise only structured-output-capable models — every
# selectable model must be able to run the scorer.
_STRUCTURED_OUTPUT_PREFIXES = ("gpt-4o", "gpt-4.1", "gpt-5", "o1", "o3", "o4")
_UNSUPPORTED_MARKERS = (
    "audio",            # gpt-4o-audio-* — speech I/O, no structured outputs
    "realtime",         # gpt-4o-realtime-* — realtime API only
    "transcribe",       # gpt-4o-transcribe — audio transcription
    "tts",              # gpt-4o-mini-tts — text-to-speech
    "search",           # gpt-4o-search-preview — search-tuned, no structured outputs
    "o1-mini",          # reasoning models without Structured Outputs support
    "o1-preview",
    "gpt-4o-2024-05-13",  # first gpt-4o snapshot, predates Structured Outputs
)


def _supports_structured_outputs(model_id: str) -> bool:
    if not model_id.startswith(_STRUCTURED_OUTPUT_PREFIXES):
        return False
    return not any(marker in model_id for marker in _UNSUPPORTED_MARKERS)


class OpenAIAvailableModelsProvider(AvailableModelsProvider):
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def list_models(self) -> list[AvailableModel]:
        client = OpenAI(api_key=self._api_key)
        models = [
            AvailableModel(model=m.id, company="OpenAI")
            for m in client.models.list()
            if _supports_structured_outputs(m.id)
        ]
        return sorted(models, key=lambda m: m.model)

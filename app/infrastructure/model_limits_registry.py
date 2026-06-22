from app.application.ports import ModelLimits, ModelLimitsRegistry

_LIMITS: dict[str, ModelLimits] = {
    "gemini-2.5-pro":       ModelLimits(rpm=5,  tpm=1_000_000, rpd=25),
    "gemini-2.5-flash":     ModelLimits(rpm=10, tpm=250_000,   rpd=500),
    "gemini-2.0-flash":     ModelLimits(rpm=15, tpm=1_000_000, rpd=1500),
    "gemini-2.0-flash-lite":ModelLimits(rpm=30, tpm=1_000_000, rpd=1500),
    "gemini-1.5-pro":       ModelLimits(rpm=2,  tpm=32_000,    rpd=50),
    "gemini-1.5-flash":     ModelLimits(rpm=15, tpm=1_000_000, rpd=1500),
    "gemini-1.5-flash-8b":  ModelLimits(rpm=15, tpm=1_000_000, rpd=1500),
}


class HardcodedModelLimitsRegistry(ModelLimitsRegistry):
    def get_limits(self, model: str) -> ModelLimits | None:
        return _LIMITS.get(model)

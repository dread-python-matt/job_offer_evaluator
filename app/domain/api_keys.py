"""Pure helpers for presenting stored API keys without exposing the secret."""

# How much of a key the display hint reveals: a short leading prefix and the last four
# characters. Keys shorter than this are fully masked so the hint never shows the whole
# secret (real provider keys are far longer, so this only guards degenerate input).
_HINT_PREFIX = 3
_HINT_SUFFIX = 4


def mask_key(plain: str) -> str:
    """A non-secret display hint for a stored key, e.g. ``sk-…1234``. Never returns the
    full key; if the key is too short to hint without revealing all of it, it is fully
    masked."""
    if len(plain) <= _HINT_PREFIX + _HINT_SUFFIX:
        return "…"
    return f"{plain[:_HINT_PREFIX]}…{plain[-_HINT_SUFFIX:]}"

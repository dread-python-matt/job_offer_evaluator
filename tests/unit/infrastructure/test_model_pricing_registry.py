from app.infrastructure.model_pricing_registry import HardcodedModelPricingRegistry

# Models the app can advertise/select today (OpenAI structured-output families + the Gemini
# set). Each MUST resolve to a price — an unpriced model's usage is counted as $0 and would
# silently bypass the budget, so a new family that slips in here should fail this test.
_SUPPORTED_MODELS = [
    "gpt-4o", "gpt-4o-2024-08-06", "gpt-4o-mini",
    "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano",
    "gpt-5", "o1", "o1-mini", "o3", "o3-mini", "o4-mini",
    "gemini-2.5-pro", "gemini-2.5-flash",
    "gemini-2.0-flash", "gemini-2.0-flash-lite",
    "gemini-1.5-pro", "gemini-1.5-flash", "gemini-1.5-flash-8b",
]


def test_every_supported_model_resolves_to_a_price():
    reg = HardcodedModelPricingRegistry()
    unpriced = [m for m in _SUPPORTED_MODELS if reg.get_price(m) is None]
    assert unpriced == []


def test_longest_prefix_wins_so_dated_snapshots_inherit_their_family_price():
    reg = HardcodedModelPricingRegistry()
    assert reg.get_price("gpt-4o-2024-08-06") == reg.get_price("gpt-4o")


_OPENAI_MODELS = [
    "gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano",
    "gpt-5", "o1", "o1-mini", "o3", "o3-mini", "o4-mini",
]
_GEMINI_MODELS = [
    "gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash",
    "gemini-2.0-flash-lite", "gemini-1.5-pro", "gemini-1.5-flash", "gemini-1.5-flash-8b",
]


def test_openai_models_have_a_cached_input_rate_below_their_input_rate():
    # OpenAI bills prompt-cache hits at a lower rate; pricing it accurately is the point of
    # the cached-input support, so every OpenAI family must carry a cached rate.
    reg = HardcodedModelPricingRegistry()
    for model in _OPENAI_MODELS:
        price = reg.get_price(model)
        assert price is not None
        assert price.cached_input_per_million is not None, model
        assert price.cached_input_per_million < price.input_per_million, model


def test_gemini_models_have_no_cached_rate_so_pricing_is_unchanged():
    # The cached-input change is OpenAI-only; Gemini keeps no cached rate and so falls back
    # to the normal input rate (its behavior is left exactly as it was).
    reg = HardcodedModelPricingRegistry()
    for model in _GEMINI_MODELS:
        price = reg.get_price(model)
        assert price is not None
        assert price.cached_input_per_million is None, model


def test_flash_lite_is_priced_below_flash_rather_than_inheriting_its_parent():
    # "gemini-2.0-flash-lite" used to fall through to the "gemini-2.0-flash" prefix and be
    # overpriced; it has its own (cheaper) entry now, and longest-prefix match picks it.
    reg = HardcodedModelPricingRegistry()
    lite = reg.get_price("gemini-2.0-flash-lite")
    flash = reg.get_price("gemini-2.0-flash")
    assert lite is not None
    assert lite.input_per_million < flash.input_per_million

from app.application.ai_scoring_context import AiScoringContext


def _make_use_case(label: str):
    """Returns a distinct sentinel object to verify identity."""
    return object()


def test_use_case_returns_initial_use_case():
    initial = _make_use_case("initial")
    context = AiScoringContext(
        initial_model="gemini-2.0-flash",
        initial_use_case=initial,
        build_use_case=lambda model: _make_use_case(model),
        configure_sdk=lambda model: None,
    )

    assert context.use_case is initial


def test_active_model_reflects_initial_model():
    context = AiScoringContext(
        initial_model="gemini-2.0-flash",
        initial_use_case=object(),
        build_use_case=lambda model: object(),
        configure_sdk=lambda model: None,
    )

    assert context.active_model == "gemini-2.0-flash"


def test_select_model_replaces_use_case():
    new_use_case = object()
    context = AiScoringContext(
        initial_model="gemini-2.0-flash",
        initial_use_case=object(),
        build_use_case=lambda model: new_use_case,
        configure_sdk=lambda model: None,
    )

    context.select_model("gpt-4o")

    assert context.use_case is new_use_case


def test_select_model_updates_active_model():
    context = AiScoringContext(
        initial_model="gemini-2.0-flash",
        initial_use_case=object(),
        build_use_case=lambda model: object(),
        configure_sdk=lambda model: None,
    )

    context.select_model("gpt-4o")

    assert context.active_model == "gpt-4o"


def test_select_model_calls_configure_sdk_with_new_model():
    configured: list[str] = []

    context = AiScoringContext(
        initial_model="gemini-2.0-flash",
        initial_use_case=object(),
        build_use_case=lambda model: object(),
        configure_sdk=configured.append,
    )

    context.select_model("gpt-4o")

    assert configured == ["gpt-4o"]


def test_select_model_passes_model_to_build_use_case():
    built_with: list[str] = []

    def build(model):
        built_with.append(model)
        return object()

    context = AiScoringContext(
        initial_model="gemini-2.0-flash",
        initial_use_case=object(),
        build_use_case=build,
        configure_sdk=lambda model: None,
    )

    context.select_model("gpt-4o")

    assert built_with == ["gpt-4o"]


def test_select_model_configure_sdk_is_called_before_build():
    order: list[str] = []

    context = AiScoringContext(
        initial_model="gemini-2.0-flash",
        initial_use_case=object(),
        build_use_case=lambda model: order.append("build") or object(),
        configure_sdk=lambda model: order.append("configure"),
    )

    context.select_model("gpt-4o")

    assert order == ["configure", "build"]

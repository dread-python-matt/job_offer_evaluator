from app.application.ai_scoring_context import AiScoringContext
from app.application.ports import SelectedModelRepository


class FakeSelectedModelRepository(SelectedModelRepository):
    def __init__(self, model: str | None = None) -> None:
        self.model = model

    def get(self) -> str | None:
        return self.model

    def set(self, model: str) -> None:
        self.model = model


def test_active_model_falls_back_to_default_when_nothing_selected():
    context = AiScoringContext(
        repository=FakeSelectedModelRepository(None),
        build_use_case=lambda model: object(),
        configure_sdk=lambda model: None,
        default_model="gemini-2.0-flash",
    )

    assert context.active_model == "gemini-2.0-flash"


def test_active_model_reflects_persisted_selection():
    context = AiScoringContext(
        repository=FakeSelectedModelRepository("gpt-4o"),
        build_use_case=lambda model: object(),
        configure_sdk=lambda model: None,
        default_model="gemini-2.0-flash",
    )

    assert context.active_model == "gpt-4o"


def test_use_case_is_built_for_the_active_model():
    context = AiScoringContext(
        repository=FakeSelectedModelRepository(None),
        build_use_case=lambda model: f"use_case::{model}",
        configure_sdk=lambda model: None,
        default_model="gemini-2.0-flash",
    )

    assert context.use_case == "use_case::gemini-2.0-flash"


def test_use_case_is_cached_between_calls():
    builds: list[str] = []
    context = AiScoringContext(
        repository=FakeSelectedModelRepository("gpt-4o"),
        build_use_case=lambda model: builds.append(model) or object(),
        configure_sdk=lambda model: None,
    )

    first = context.use_case
    second = context.use_case

    assert first is second
    assert builds == ["gpt-4o"]


def test_select_model_persists_and_rebuilds():
    repo = FakeSelectedModelRepository("gpt-4o")
    new_use_case = object()
    context = AiScoringContext(
        repository=repo,
        build_use_case=lambda model: new_use_case,
        configure_sdk=lambda model: None,
    )

    context.select_model("gemini-2.0-flash")

    assert repo.get() == "gemini-2.0-flash"
    assert context.active_model == "gemini-2.0-flash"
    assert context.use_case is new_use_case


def test_use_case_rebuilds_when_persisted_model_changes_externally():
    """A switch made by another worker (in the shared repo) is picked up on next use."""
    repo = FakeSelectedModelRepository("gpt-4o")
    context = AiScoringContext(
        repository=repo,
        build_use_case=lambda model: f"use_case::{model}",
        configure_sdk=lambda model: None,
    )

    assert context.use_case == "use_case::gpt-4o"
    repo.set("gemini-2.0-flash")  # another worker selected a different model
    assert context.use_case == "use_case::gemini-2.0-flash"


def test_configure_sdk_runs_before_build_on_select():
    order: list[str] = []
    context = AiScoringContext(
        repository=FakeSelectedModelRepository("gpt-4o"),
        build_use_case=lambda model: order.append("build") or object(),
        configure_sdk=lambda model: order.append("configure"),
    )

    context.select_model("gemini-2.0-flash")

    assert order == ["configure", "build"]

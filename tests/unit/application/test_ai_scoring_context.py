from app.application.ai_scoring_context import AiScoringContext
from app.application.ports import SelectedModelRepository


class FakeSelectedModelRepository(SelectedModelRepository):
    def __init__(self, models: dict[str, str] | None = None) -> None:
        self._models = dict(models or {})

    def get(self, user_id: str) -> str | None:
        return self._models.get(user_id)

    def set(self, user_id: str, model: str) -> None:
        self._models[user_id] = model


def test_active_model_falls_back_to_default_when_user_has_no_selection():
    context = AiScoringContext(
        repository=FakeSelectedModelRepository(),
        build_use_case=lambda user_id, model: object(),
        configure_sdk=lambda model: None,
        default_model="gemini-2.0-flash",
    )

    assert context.active_model_for("alice") == "gemini-2.0-flash"


def test_active_model_reflects_the_users_persisted_selection():
    context = AiScoringContext(
        repository=FakeSelectedModelRepository({"alice": "gpt-4o"}),
        build_use_case=lambda user_id, model: object(),
        configure_sdk=lambda model: None,
        default_model="gemini-2.0-flash",
    )

    assert context.active_model_for("alice") == "gpt-4o"


def test_two_users_can_have_different_active_models():
    context = AiScoringContext(
        repository=FakeSelectedModelRepository({"alice": "gpt-4o"}),
        build_use_case=lambda user_id, model: object(),
        configure_sdk=lambda model: None,
        default_model="gemini-2.0-flash",
    )

    assert context.active_model_for("alice") == "gpt-4o"
    assert context.active_model_for("bob") == "gemini-2.0-flash"


def test_use_case_is_built_for_the_users_active_model():
    context = AiScoringContext(
        repository=FakeSelectedModelRepository(),
        build_use_case=lambda user_id, model: f"use_case::{user_id}::{model}",
        configure_sdk=lambda model: None,
        default_model="gemini-2.0-flash",
    )

    assert context.use_case_for("alice") == "use_case::alice::gemini-2.0-flash"


def test_use_case_is_built_per_user_and_not_shared_across_users():
    # Each user's use case is bound to that user's own API key, so two users on the same
    # model get separately built use cases (no cross-user sharing).
    builds: list[tuple[str, str]] = []
    context = AiScoringContext(
        repository=FakeSelectedModelRepository({"alice": "gpt-4o", "bob": "gpt-4o"}),
        build_use_case=lambda user_id, model: builds.append((user_id, model)) or object(),
        configure_sdk=lambda model: None,
    )

    first = context.use_case_for("alice")
    second = context.use_case_for("bob")

    assert first is not second
    assert builds == [("alice", "gpt-4o"), ("bob", "gpt-4o")]


def test_use_case_is_built_once_per_user_model_and_then_cached():
    builds: list[tuple[str, str]] = []
    context = AiScoringContext(
        repository=FakeSelectedModelRepository({"alice": "gpt-4o"}),
        build_use_case=lambda user_id, model: builds.append((user_id, model)) or object(),
        configure_sdk=lambda model: None,
    )

    first = context.use_case_for("alice")
    second = context.use_case_for("alice")

    assert first is second
    assert builds == [("alice", "gpt-4o")]


def test_select_model_persists_and_switches_the_users_use_case():
    repo = FakeSelectedModelRepository({"alice": "gpt-4o"})
    context = AiScoringContext(
        repository=repo,
        build_use_case=lambda user_id, model: f"use_case::{user_id}::{model}",
        configure_sdk=lambda model: None,
    )

    context.select_model("alice", "gemini-2.0-flash")

    assert repo.get("alice") == "gemini-2.0-flash"
    assert context.use_case_for("alice") == "use_case::alice::gemini-2.0-flash"


def test_use_case_picks_up_an_external_model_change():
    repo = FakeSelectedModelRepository({"alice": "gpt-4o"})
    context = AiScoringContext(
        repository=repo,
        build_use_case=lambda user_id, model: f"use_case::{user_id}::{model}",
        configure_sdk=lambda model: None,
    )

    assert context.use_case_for("alice") == "use_case::alice::gpt-4o"
    repo.set("alice", "gemini-2.0-flash")  # another worker switched this user's model
    assert context.use_case_for("alice") == "use_case::alice::gemini-2.0-flash"


def test_configure_sdk_runs_before_build():
    order: list[str] = []
    context = AiScoringContext(
        repository=FakeSelectedModelRepository({"alice": "gpt-4o"}),
        build_use_case=lambda user_id, model: order.append("build") or object(),
        configure_sdk=lambda model: order.append("configure"),
    )

    context.select_model("alice", "gemini-2.0-flash")

    assert order == ["configure", "build"]


def test_invalidate_drops_all_cached_use_cases_for_a_user():
    # A user's keys can change (add/delete/rotate). A cached use case is bound to the key
    # that was current when it was built, so invalidate must drop it — otherwise the user
    # keeps replaying a stale (possibly deleted) key until eviction or restart.
    builds: list[tuple[str, str]] = []
    context = AiScoringContext(
        repository=FakeSelectedModelRepository({"alice": "gpt-4o", "bob": "gpt-4o"}),
        build_use_case=lambda user_id, model: builds.append((user_id, model)) or object(),
        configure_sdk=lambda model: None,
    )

    context.use_case_for("alice")
    context.use_case_for("bob")
    context.invalidate("alice")
    context.use_case_for("alice")  # rebuilds with the user's current key
    context.use_case_for("bob")  # untouched — still cached

    assert builds == [("alice", "gpt-4o"), ("bob", "gpt-4o"), ("alice", "gpt-4o")]


def test_invalidate_an_uncached_user_is_harmless():
    context = AiScoringContext(
        repository=FakeSelectedModelRepository(),
        build_use_case=lambda user_id, model: object(),
        configure_sdk=lambda model: None,
    )

    context.invalidate("nobody")  # must not raise


def test_cache_is_bounded_and_evicts_least_recently_used():
    # The cache must not grow without bound as users/models accumulate; once full it evicts
    # the least-recently-used entry, and a cache hit counts as a recent use.
    builds: list[str] = []
    context = AiScoringContext(
        repository=FakeSelectedModelRepository({"alice": "m1", "bob": "m2", "carol": "m3"}),
        build_use_case=lambda user_id, model: builds.append(user_id) or object(),
        configure_sdk=lambda model: None,
        max_entries=2,
    )

    context.use_case_for("alice")
    context.use_case_for("bob")
    context.use_case_for("alice")  # hit → alice is now most-recently-used
    context.use_case_for("carol")  # over capacity → evicts the LRU entry (bob)

    context.use_case_for("alice")  # survived → no rebuild
    context.use_case_for("bob")  # was evicted → rebuilds

    assert builds == ["alice", "bob", "carol", "bob"]

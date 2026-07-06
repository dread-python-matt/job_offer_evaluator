import pytest

from app.scripts.setup import SetupOutcome, run_setup


def _recorder(calls: list[str], name: str, ret: object = None):
    """A no-arg step that records it ran (and in what order) and returns `ret`."""

    def _step():
        calls.append(name)
        return ret

    return _step


def test_runs_the_steps_in_order_without_the_demo_login():
    calls: list[str] = []

    outcome = run_setup(
        ensure_database_ready=_recorder(calls, "ready"),
        migrate=_recorder(calls, "migrate"),
        seed_offers=_recorder(calls, "offers", ret=54),
        seed_demo_user=None,
    )

    assert calls == ["ready", "migrate", "offers"]
    assert outcome == SetupOutcome(offers_seeded=54, demo_user_created=None)


def test_seeds_the_demo_login_last_when_requested():
    calls: list[str] = []

    outcome = run_setup(
        ensure_database_ready=_recorder(calls, "ready"),
        migrate=_recorder(calls, "migrate"),
        seed_offers=_recorder(calls, "offers", ret=54),
        seed_demo_user=_recorder(calls, "demo", ret=True),
    )

    assert calls == ["ready", "migrate", "offers", "demo"]
    assert outcome.demo_user_created is True


def test_reports_a_preexisting_demo_login_as_not_created():
    outcome = run_setup(
        ensure_database_ready=lambda: None,
        migrate=lambda: None,
        seed_offers=lambda: 54,
        seed_demo_user=lambda: False,  # already existed
    )

    assert outcome.demo_user_created is False


def test_aborts_before_migrating_or_seeding_when_the_database_is_unreachable():
    # The readiness check gates everything: a down database must stop setup before it runs any
    # migration or write, so the failure surfaces cleanly rather than half-way through.
    calls: list[str] = []

    def _unreachable() -> None:
        raise RuntimeError("database down")

    with pytest.raises(RuntimeError):
        run_setup(
            ensure_database_ready=_unreachable,
            migrate=_recorder(calls, "migrate"),
            seed_offers=_recorder(calls, "offers"),
            seed_demo_user=None,
        )

    assert calls == []  # nothing ran after the failed readiness check

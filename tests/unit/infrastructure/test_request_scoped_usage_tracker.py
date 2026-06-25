import asyncio
import threading

from app.application.ports import ModelUsage
from app.infrastructure.request_scoped_usage_tracker import RequestScopedModelUsageTracker


def _usage(label: str) -> ModelUsage:
    return ModelUsage(label=label, input_tokens=1, output_tokens=1)


def test_record_then_flush_returns_records_and_clears():
    tracker = RequestScopedModelUsageTracker()
    tracker.begin()

    tracker.record(_usage("a"))
    tracker.record(_usage("b"))

    assert [u.label for u in tracker.flush()] == ["a", "b"]
    assert tracker.flush() == []  # drained


def test_begin_discards_anything_not_yet_flushed():
    tracker = RequestScopedModelUsageTracker()
    tracker.begin()
    tracker.record(_usage("stale"))

    tracker.begin()  # a new request opens a clean scope

    assert tracker.flush() == []


def test_tasks_spawned_after_begin_share_the_request_scope():
    # Mirrors the real flow: begin() in the (sync) parent context, then concurrent scoring
    # tasks under asyncio.run append into that same scope, read back by flush().
    tracker = RequestScopedModelUsageTracker()

    def handle_request() -> list[str]:
        tracker.begin()

        async def score_all() -> None:
            async def score(label: str) -> None:
                tracker.record(_usage(label))

            await asyncio.gather(score("x"), score("y"), score("z"))

        asyncio.run(score_all())
        return [u.label for u in tracker.flush()]

    assert sorted(handle_request()) == ["x", "y", "z"]


def test_usage_does_not_bleed_across_concurrent_threads():
    # One shared tracker instance, two interleaved "requests" on different threads: each
    # must see only its own usage (the cross-tenant misattribution this design prevents).
    tracker = RequestScopedModelUsageTracker()
    results: dict[str, list[str]] = {}
    both_recorded = threading.Barrier(2)

    def handle_request(name: str) -> None:
        tracker.begin()
        tracker.record(_usage(name))
        both_recorded.wait()  # force interleaving: both record before either flushes
        results[name] = [u.label for u in tracker.flush()]

    threads = [threading.Thread(target=handle_request, args=(n,)) for n in ("req-1", "req-2")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results["req-1"] == ["req-1"]
    assert results["req-2"] == ["req-2"]

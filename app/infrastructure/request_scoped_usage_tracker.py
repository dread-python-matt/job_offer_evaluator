from contextvars import ContextVar

from app.application.ports import ModelUsage, ModelUsageTracker


class RequestScopedModelUsageTracker(ModelUsageTracker):
    """Per-request token-usage accounting backed by a `ContextVar`.

    A single shared instance is safe to reuse across all requests: each request owns its own
    list of records via the context variable, so concurrent AI matches (different threads /
    different users) never see each other's usage. This prevents the cross-tenant
    misattribution that a process-wide list would cause — where one request's `flush()` could
    drain and stamp another user's tokens.

    `begin()` must be called at the start of a request, in the same context that will later
    call `flush()`, **before** any concurrent scoring tasks are spawned. Each `asyncio` task
    copies the current context at creation, so the fresh list set by `begin()` is shared by
    all of that request's scoring tasks (which only append) and read back by `flush()`.
    """

    _records: ContextVar[list[ModelUsage] | None] = ContextVar(
        "model_usage_records", default=None
    )

    def begin(self) -> None:
        self._records.set([])

    def record(self, usage: ModelUsage) -> None:
        records = self._records.get()
        if records is None:
            # No scope was opened (begin() not called); start one lazily so usage isn't lost.
            records = []
            self._records.set(records)
        records.append(usage)

    def flush(self) -> list[ModelUsage]:
        records = self._records.get() or []
        self._records.set([])
        return list(records)

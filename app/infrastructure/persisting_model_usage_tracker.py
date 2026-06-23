from app.application.ports import ModelUsage, ModelUsageRepository, ModelUsageTracker


class PersistingModelUsageTracker(ModelUsageTracker):
    """Adapter: wraps a ModelUsageRepository to satisfy the ModelUsageTracker port.
    Writes are fire-and-forget (persisted immediately on record()); flush() returns
    nothing because there is no in-memory buffer to drain."""

    def __init__(self, repository: ModelUsageRepository) -> None:
        self._repository = repository

    def record(self, usage: ModelUsage) -> None:
        self._repository.save(usage)

    def flush(self) -> list[ModelUsage]:
        return []

from app.application.ports import ModelUsage, ModelUsageTracker


class CompositeModelUsageTracker(ModelUsageTracker):
    def __init__(self, trackers: list[ModelUsageTracker]) -> None:
        self._trackers = trackers

    def record(self, usage: ModelUsage) -> None:
        for tracker in self._trackers:
            tracker.record(usage)

    def flush(self) -> list[ModelUsage]:
        results: list[ModelUsage] = []
        for tracker in self._trackers:
            results.extend(tracker.flush())
        return results

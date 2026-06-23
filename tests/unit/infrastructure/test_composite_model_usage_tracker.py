from app.application.ports import ModelUsage, ModelUsageTracker
from app.infrastructure.composite_model_usage_tracker import CompositeModelUsageTracker


class RecordingTracker(ModelUsageTracker):
    def __init__(self) -> None:
        self.recorded: list[ModelUsage] = []

    def record(self, usage: ModelUsage) -> None:
        self.recorded.append(usage)

    def flush(self) -> list[ModelUsage]:
        flushed, self.recorded = self.recorded, []
        return flushed


def test_composite_broadcasts_to_all_trackers():
    t1, t2 = RecordingTracker(), RecordingTracker()
    composite = CompositeModelUsageTracker([t1, t2])
    usage = ModelUsage(label="scoring", input_tokens=100, output_tokens=50)

    composite.record(usage)

    assert t1.recorded == [usage]
    assert t2.recorded == [usage]


def test_composite_with_single_tracker():
    t = RecordingTracker()
    composite = CompositeModelUsageTracker([t])
    usage = ModelUsage(label="scoring", input_tokens=10, output_tokens=5)

    composite.record(usage)

    assert t.recorded == [usage]

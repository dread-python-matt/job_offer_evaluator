import logging

from app.application.ports import ModelUsage, ModelUsageTracker

_logger = logging.getLogger(__name__)


class LoggingModelUsageTracker(ModelUsageTracker):
    def record(self, usage: ModelUsage) -> None:
        _logger.info(
            "[%s] input_tokens=%d output_tokens=%d total=%d",
            usage.label,
            usage.input_tokens,
            usage.output_tokens,
            usage.input_tokens + usage.output_tokens,
        )

    def flush(self) -> list[ModelUsage]:
        return []

import logging

from app.application.ports import ModelUsage
from app.infrastructure.logging_model_usage_tracker import LoggingModelUsageTracker


def test_record_logs_label_and_token_counts(caplog):
    tracker = LoggingModelUsageTracker()

    with caplog.at_level(logging.INFO):
        tracker.record(ModelUsage(label="scoring", input_tokens=150, output_tokens=60))

    assert "scoring" in caplog.text
    assert "150" in caplog.text
    assert "60" in caplog.text


def test_record_logs_translation_label(caplog):
    tracker = LoggingModelUsageTracker()

    with caplog.at_level(logging.INFO):
        tracker.record(ModelUsage(label="translation", input_tokens=40, output_tokens=35))

    assert "translation" in caplog.text

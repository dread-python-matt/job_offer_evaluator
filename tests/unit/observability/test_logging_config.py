import json
import logging
from collections.abc import Iterator

import pytest

from app.observability.logging_config import (
    ConsoleLogFormatter,
    JsonLogFormatter,
    RequestIdFilter,
    configure_logging,
)
from app.observability.request_context import bind_request_id, reset_request_id


def _record(msg: str = "hello %s", *, args=("world",), **extra) -> logging.LogRecord:
    record = logging.LogRecord(
        name="app.demo",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg=msg,
        args=args,
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


# --- JSON formatter ---


def test_json_formatter_emits_standard_fields():
    payload = json.loads(JsonLogFormatter().format(_record()))

    assert payload["level"] == "INFO"
    assert payload["logger"] == "app.demo"
    assert payload["message"] == "hello world"  # %-args are rendered
    assert payload["request_id"] == "-"  # unset when no filter ran
    assert payload["timestamp"].endswith("+00:00")  # ISO-8601, UTC


def test_json_formatter_includes_extra_fields():
    payload = json.loads(JsonLogFormatter().format(_record(offer_id=7, model="gemini")))

    assert payload["offer_id"] == 7
    assert payload["model"] == "gemini"


def test_json_formatter_renders_exception_traceback():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = logging.LogRecord(
            "app.demo", logging.ERROR, __file__, 1, "failed", (), sys.exc_info()
        )

    payload = json.loads(JsonLogFormatter().format(record))

    assert "ValueError: boom" in payload["exception"]


def test_json_formatter_never_drops_a_non_serializable_extra():
    payload = json.loads(JsonLogFormatter().format(_record(obj=object())))

    assert "obj" in payload  # degraded to a string rather than raising


# --- console formatter ---


def test_console_formatter_includes_request_id_placeholder():
    line = ConsoleLogFormatter().format(_record(request_id="-"))

    assert "[-]" in line
    assert "app.demo: hello world" in line


# --- request id filter ---


def test_filter_stamps_bound_request_id():
    token = bind_request_id("rid-1")
    try:
        record = _record()
        RequestIdFilter().filter(record)
        assert record.request_id == "rid-1"
    finally:
        reset_request_id(token)


def test_filter_uses_placeholder_when_unbound():
    record = _record()
    RequestIdFilter().filter(record)

    assert record.request_id == "-"


def test_filter_does_not_clobber_explicit_request_id():
    record = _record(request_id="explicit")
    RequestIdFilter().filter(record)

    assert record.request_id == "explicit"


# --- configure_logging ---


@pytest.fixture
def restore_root_logger() -> Iterator[None]:
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    saved_levels = {
        name: logging.getLogger(name).level for name in ("httpx", "uvicorn")
    }
    try:
        yield
    finally:
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)
        for name, level in saved_levels.items():
            logging.getLogger(name).setLevel(level)


def test_configure_logging_installs_single_json_handler(restore_root_logger):
    configure_logging(level="DEBUG", fmt="json")

    root = logging.getLogger()
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0].formatter, JsonLogFormatter)
    assert root.level == logging.DEBUG
    assert any(isinstance(f, RequestIdFilter) for f in root.handlers[0].filters)


def test_configure_logging_is_idempotent(restore_root_logger):
    configure_logging(fmt="json")
    configure_logging(fmt="console")

    root = logging.getLogger()
    assert len(root.handlers) == 1  # replaced, not stacked
    assert isinstance(root.handlers[0].formatter, ConsoleLogFormatter)


def test_configure_logging_quiets_noisy_clients(restore_root_logger):
    configure_logging()

    assert logging.getLogger("httpx").level == logging.WARNING


def test_configure_logging_lets_uvicorn_propagate(restore_root_logger):
    configure_logging()

    uvicorn_logger = logging.getLogger("uvicorn")
    assert uvicorn_logger.propagate is True
    assert uvicorn_logger.handlers == []

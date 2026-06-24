import logging

from app.infrastructure.llm_logging import configure_llm_logging


def _reset(name: str) -> None:
    logging.getLogger(name).setLevel(logging.NOTSET)


def test_enabling_sets_openai_traffic_loggers_to_debug():
    for name in ("openai", "httpx", "httpcore"):
        _reset(name)

    configure_llm_logging(True)

    for name in ("openai", "httpx", "httpcore"):
        assert logging.getLogger(name).level == logging.DEBUG


def test_disabled_is_a_noop():
    _reset("openai")

    configure_llm_logging(False)

    assert logging.getLogger("openai").level == logging.NOTSET

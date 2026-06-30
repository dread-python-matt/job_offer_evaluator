"""Process-wide logging setup: one root handler writing structured logs to stdout.

This is the single source of truth for how the app logs (replacing the ad-hoc
`logging.basicConfig` calls that used to live in `main.py` / `llm_logging.py`). It is a
cross-cutting concern wired from the composition root, so it lives alongside `config.py`
rather than inside a layer.

Design choices (see README "Logging"):
- **stdlib only.** Every module already logs via `logging.getLogger(__name__)`; a JSON
  `Formatter` upgrades all of them to structured output with zero call-site changes and no
  new dependency.
- **stdout.** 12-factor: the process logs to stdout and the platform (Docker/K8s/an agent)
  ships it. JSON lines are what aggregators (Loki, ELK, Datadog, CloudWatch) want.
- **correlation.** A `RequestIdFilter` stamps the current request id (a `contextvar`, see
  `request_context`) onto every record, so a request's lines can be grepped/queried together.
"""

import datetime as dt
import json
import logging
import sys
from typing import Any

from app.observability.request_context import get_request_id

# Attributes the stdlib puts on every LogRecord (plus a few added during formatting / by
# third parties). Everything *else* on a record came from a caller's `extra={...}` and is
# emitted as a structured field, so `logger.info("done", extra={"offer_id": 7})` just works.
# `color_message` is injected by uvicorn's loggers; `request_id` we render explicitly.
_STANDARD_ATTRS = frozenset(vars(logging.makeLogRecord({}))) | {
    "message",
    "asctime",
    "taskName",
    "color_message",
    "request_id",
}

# Per-request INFO spam from the HTTP client used for outbound LLM/provider calls. Quieted to
# WARNING by default; LLM_DEBUG (configure_llm_logging) re-raises these to DEBUG when needed.
_NOISY_LOGGERS = ("httpx", "httpcore")

# Uvicorn's own loggers. With `log_config=None` passed to `uvicorn.run` they have no handlers
# and propagate to root, so they pick up our formatter — server and app logs share one format.
_UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


class RequestIdFilter(logging.Filter):
    """Stamps the current request id onto each record as `request_id`.

    Attached to the handler so it runs for every record reaching it, including records from
    third-party loggers that never heard of this app. Records emitted outside a request
    (startup, shutdown, background work) get the `default` placeholder."""

    def __init__(self, default: str = "-") -> None:
        super().__init__()
        self._default = default

    def filter(self, record: logging.LogRecord) -> bool:
        # Don't clobber an id a caller set explicitly via `extra={"request_id": ...}`.
        if not hasattr(record, "request_id"):
            record.request_id = get_request_id() or self._default
        return True


class JsonLogFormatter(logging.Formatter):
    """Renders each record as a single-line JSON object for log aggregators."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": dt.datetime.fromtimestamp(record.created, dt.UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        # Structured fields a caller attached via `extra={...}`.
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS and key not in payload:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)
        # default=str keeps logging robust: an unexpected non-JSON value degrades to its repr
        # instead of raising inside the logging call site.
        return json.dumps(payload, default=str, ensure_ascii=False)


class ConsoleLogFormatter(logging.Formatter):
    """Human-readable single line for local dev; surfaces the request id inline."""

    def __init__(self) -> None:
        super().__init__(
            fmt="%(asctime)s %(levelname)-8s [%(request_id)s] %(name)s: %(message)s",
        )


def _build_formatter(fmt: str) -> logging.Formatter:
    return JsonLogFormatter() if fmt == "json" else ConsoleLogFormatter()


def configure_logging(*, level: str | int = "INFO", fmt: str = "json") -> None:
    """Install the root logging handler (stdout) with the chosen format and level.

    Idempotent: re-running replaces the handler instead of stacking duplicates, so repeated
    imports or test setup don't multiply log lines. `fmt` is "json" (default, aggregator
    -friendly) or "console" (human-readable). Call this once, first thing, from the
    composition root — before anything logs.
    """
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(_build_formatter(fmt))
    handler.addFilter(RequestIdFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Route uvicorn through our handler; its access log is left to the middleware (richer:
    # request id + duration), so `uvicorn.run(access_log=False)` keeps it from doubling up.
    for name in _UVICORN_LOGGERS:
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True

    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

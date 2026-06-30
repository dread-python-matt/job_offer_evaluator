"""Request-scoped correlation id, carried across async boundaries via contextvars.

A single id is bound at the edge (the request-logging middleware) for each incoming HTTP
request and read back by the logging filter, so every log line emitted while handling that
request — in any layer, including code awaited in concurrent asyncio tasks (e.g. the AI
match's bounded `gather` over offers) — carries the same id. We use `contextvars` rather than
thread-locals precisely because the value must follow `await` hops and be copied into child
tasks; thread-locals would be wrong under asyncio.
"""

from contextvars import ContextVar, Token

# `None` (not "") is the unset sentinel so the filter can tell "outside any request" (startup,
# shutdown, background work) apart from a request that genuinely has a blank id.
_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def bind_request_id(request_id: str) -> Token[str | None]:
    """Bind the id for the current context; returns a token to restore the previous value."""
    return _request_id.set(request_id)


def get_request_id() -> str | None:
    """The id bound to the current context, or `None` outside a request."""
    return _request_id.get()


def reset_request_id(token: Token[str | None]) -> None:
    """Restore the value captured before the matching `bind_request_id`.

    The middleware resets in a `finally` so ids never leak between requests sharing a context
    (e.g. Starlette's TestClient, which does not spawn a fresh task per call)."""
    _request_id.reset(token)

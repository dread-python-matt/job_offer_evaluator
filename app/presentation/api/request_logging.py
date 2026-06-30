"""Per-request correlation id + structured access logging.

Implemented as **raw ASGI** (not `BaseHTTPMiddleware`) on purpose: `BaseHTTPMiddleware` runs
the downstream app in a separate anyio task, so a `contextvar` set in its `dispatch` would not
be visible to the endpoint or to log lines the endpoint (and use cases) emit. A plain ASGI
middleware sets the id in the very same context that runs the route, so the whole request —
including the AI match's concurrent scoring tasks, which copy the context — shares one id.

What it does per HTTP request:
  1. adopt an inbound `X-Request-ID` (so a gateway/SPA can stitch its id to ours) or mint a
     fresh UUID, and bind it for the request's context;
  2. echo it back in the `X-Request-ID` response header;
  3. emit exactly one structured access line (method, path, status, duration) when the
     request finishes — `/health` at DEBUG (probes hit it constantly), 5xx/errors at ERROR.

Only the path is logged, never the query string or body, so tokens/PII never land in logs.
"""

import logging
import time
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.observability.request_context import bind_request_id, reset_request_id

# Dedicated logger so access lines are filterable as `logger == "app.request"`.
_logger = logging.getLogger("app.request")
_HEALTH_PATH = "/health"


class RequestLoggingMiddleware:
    def __init__(self, app: ASGIApp, header_name: str = "X-Request-ID") -> None:
        self.app = app
        self._header_raw = header_name.encode("latin-1")
        self._header_lower = header_name.lower().encode("latin-1")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = self._inbound_id(scope) or uuid.uuid4().hex
        token = bind_request_id(request_id)
        start = time.perf_counter()
        # Default to 500: if the app raises before sending a response, the access line still
        # reflects a failure rather than a misleading success.
        status = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = list(message.get("headers", []))
                headers.append((self._header_raw, request_id.encode("latin-1")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            # Logged while the id is still bound, so the failure line correlates to the
            # request even though the catch-all exception handler runs further out.
            self._log_request(scope, status, start, failed=True)
            raise
        else:
            self._log_request(scope, status, start, failed=False)
        finally:
            reset_request_id(token)

    def _inbound_id(self, scope: Scope) -> str | None:
        for name, value in scope.get("headers", []):
            if name.lower() == self._header_lower:
                return value.decode("latin-1").strip() or None
        return None

    def _log_request(
        self, scope: Scope, status: int, start: float, *, failed: bool
    ) -> None:
        method = scope.get("method", "-")
        path = scope.get("path", "-")
        client = scope.get("client")
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        if failed or status >= 500:
            level = logging.ERROR
        elif path == _HEALTH_PATH:
            level = logging.DEBUG
        else:
            level = logging.INFO
        _logger.log(
            level,
            "%s %s -> %s (%sms)",
            method,
            path,
            status,
            duration_ms,
            extra={
                "event": "http_request",
                "http_method": method,
                "http_path": path,
                "http_status": status,
                "duration_ms": duration_ms,
                "client_ip": client[0] if client else None,
            },
        )

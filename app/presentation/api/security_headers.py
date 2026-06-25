from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# A strict default for a JSON API that serves no HTML and must never be framed.
_CSP = "default-src 'none'; frame-ancestors 'none'"
_HSTS = "max-age=63072000; includeSubDomains"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds defense-in-depth response headers to every response.

    Sets `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and a strict
    `Content-Security-Policy`. `Strict-Transport-Security` is sent only when `enable_hsts`
    is true (i.e. when served over HTTPS), since HSTS over plain HTTP is meaningless and
    pinning it during local HTTP development would be counterproductive.
    """

    def __init__(self, app, enable_hsts: bool = False) -> None:
        super().__init__(app)
        self._enable_hsts = enable_hsts

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Content-Security-Policy", _CSP)
        if self._enable_hsts:
            response.headers.setdefault("Strict-Transport-Security", _HSTS)
        return response

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.domain.errors import MissingProviderApiKeyError

_logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """Catch-all for unhandled exceptions: log the full traceback server-side and
    return a generic 500 so internal details (stack traces, DB errors, provider
    payloads) never leak to clients. Domain errors mapped in the routes
    (BudgetExceededError->402, AiScoringError->503) and HTTPException are unaffected."""

    @app.exception_handler(MissingProviderApiKeyError)
    async def _handle_missing_provider_key(
        request: Request, exc: MissingProviderApiKeyError
    ) -> JSONResponse:
        # Require-own-key: the user selected a model whose provider they have no key for.
        # Resolved while building the per-user scoring use case (a dependency), so it is
        # handled here rather than in the route body. 400 with a clear, actionable message.
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        _logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

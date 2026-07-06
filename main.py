"""Entry point: build the FastAPI app from the composition root and run the server.

All wiring lives in `app.composition` (see `build_app`); this module only exposes the ASGI `app`
object and the `main()` runner. Keeping `app` at module scope is required so `uvicorn.run("main:app",
...)` can import it when spawning worker processes.
"""

from app.composition import build_app
from app.config import HOST, PORT, WORKERS

app = build_app()


def main() -> None:
    import uvicorn

    # log_config=None: keep uvicorn from installing its own logging — configure_logging() (run in
    # build_app) owns the root handler and uvicorn's loggers propagate into it, so server and app
    # logs share one JSON format. access_log=False: RequestLoggingMiddleware emits richer access
    # lines (correlation id + duration), so uvicorn's plain access log would only duplicate them.
    if WORKERS > 1:
        # Multiple workers require an import string so uvicorn can spawn processes.
        uvicorn.run(
            "main:app",
            host=HOST,
            port=PORT,
            workers=WORKERS,
            log_config=None,
            access_log=False,
        )
    else:
        uvicorn.run(app, host=HOST, port=PORT, log_config=None, access_log=False)


if __name__ == "__main__":
    main()

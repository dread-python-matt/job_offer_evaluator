# syntax=docker/dockerfile:1
FROM python:3.13-slim

# uv for fast, reproducible installs.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

WORKDIR /app

# Dependencies first (cached layer): no dev deps, don't install the project yet.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Application code (+ migrations).
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini main.py ./
RUN uv sync --frozen --no-dev

# Run as a non-root user.
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser

# In a container the server must bind all interfaces (publish the port deliberately).
ENV HOST=0.0.0.0 PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Apply migrations, (re)build the offer_skill concept index, then start the API. The index build
# is best-effort (`|| true`): a failed/empty build degrades only the browse tech filter, so it
# must never block boot, whereas migrations must succeed. The indexer no-ops if the externally-owned
# `offers` table isn't present yet, so this is safe on a brand-new database.
CMD ["sh", "-c", "uv run --no-sync alembic upgrade head && (uv run --no-sync python -m app.scripts.index_offer_skills || true) && uv run --no-sync python main.py"]

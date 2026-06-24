import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DATABASE_URL = os.environ["DATABASE_URL"]
USER_PROFILE_PATH = Path(__file__).resolve().parent.parent / "DATA" / "user_profile.md"
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "gemini")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_ADMIN_KEY = os.environ.get("OPENAI_ADMIN_KEY", "")
# Seeds the budget limit only on first run; afterwards the limit is owned by the DB
# and changed via the API.
DEFAULT_BUDGET_USD = float(os.environ.get("DEFAULT_BUDGET_USD", os.environ.get("DAILY_BUDGET_USD", "5.0")))
LLM_DEBUG = os.environ.get("LLM_DEBUG", "false").strip().lower() in {"1", "true", "yes", "on"}
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:4200").split(",")
# Max offers scored by the AI in parallel per match request. Each scoring is a slow
# LLM round-trip, so this bounds latency without overrunning provider rate limits.
AI_MATCH_CONCURRENCY = int(os.environ.get("AI_MATCH_CONCURRENCY", "10"))
# Network bind. Defaults to localhost so the API isn't reachable off-box; set
# HOST=0.0.0.0 explicitly (behind auth / a gateway) for container/remote deploys.
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))
# Number of worker processes. The active model is persisted (shared across workers),
# so >1 is safe for horizontal scaling.
WORKERS = int(os.environ.get("WORKERS", "1"))
# Timeout (seconds) for outbound LLM/provider HTTP calls, so a hung provider can't
# tie up a worker indefinitely.
LLM_TIMEOUT_SECONDS = float(os.environ.get("LLM_TIMEOUT_SECONDS", "60.0"))
# Seconds to cache the provider spend figure used by the budget gate, so a burst of
# matches doesn't query the cost API every request.
BUDGET_SPEND_CACHE_TTL_SECONDS = float(os.environ.get("BUDGET_SPEND_CACHE_TTL_SECONDS", "60.0"))
# When true, block AI matches if spend can't be read (fail-closed); default fail-open.
BUDGET_FAIL_CLOSED = os.environ.get("BUDGET_FAIL_CLOSED", "false").strip().lower() in {"1", "true", "yes", "on"}
# Seconds to cache the provider's available-models list (UI loads / model switches).
MODELS_CACHE_TTL_SECONDS = float(os.environ.get("MODELS_CACHE_TTL_SECONDS", "300.0"))

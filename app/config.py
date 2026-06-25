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

# --- Email confirmation ---
# Base URL of the frontend; the registration confirmation link points at its
# /verify-email route (e.g. http://localhost:4200/verify-email?token=...).
APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:4200").rstrip("/")
# SMTP delivery. When SMTP_HOST is empty the app falls back to a console sender that only
# logs the confirmation link — a dev convenience, not real delivery.
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "true").strip().lower() in {"1", "true", "yes", "on"}
EMAIL_FROM = os.environ.get("EMAIL_FROM", "no-reply@localhost")
# How long (hours) a confirmation link stays valid.
EMAIL_VERIFICATION_TTL_HOURS = int(os.environ.get("EMAIL_VERIFICATION_TTL_HOURS", "24"))
# How long (hours) a password-reset link stays valid. Shorter than the confirmation link
# since following it grants account access.
PASSWORD_RESET_TTL_HOURS = int(os.environ.get("PASSWORD_RESET_TTL_HOURS", "1"))
# When true, verify the address is deliverable (DNS/MX lookup) at registration. Off by
# default so tests and offline runs don't depend on DNS; enable in production.
EMAIL_CHECK_DELIVERABILITY = os.environ.get("EMAIL_CHECK_DELIVERABILITY", "false").strip().lower() in {"1", "true", "yes", "on"}
LLM_DEBUG = os.environ.get("LLM_DEBUG", "false").strip().lower() in {"1", "true", "yes", "on"}
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:4200").split(",")
# Max offers scored by the AI in parallel per match request. Each scoring is a slow
# LLM round-trip, so this bounds latency without overrunning provider rate limits.
AI_MATCH_CONCURRENCY = int(os.environ.get("AI_MATCH_CONCURRENCY", "10"))

# --- Authentication ---
# Secret for signing session JWTs. MUST be overridden in production (a leaked or default
# secret lets anyone forge sessions). The dev default keeps local setup zero-config.
JWT_SECRET = os.environ.get("JWT_SECRET", "dev-insecure-change-me-0123456789abcdef")
SESSION_TTL_DAYS = int(os.environ.get("SESSION_TTL_DAYS", "7"))
# Login brute-force throttle: wrong-credential attempts allowed per (client IP, email)
# within the window before /auth/login returns 429. In-memory and per-process, so this is
# single-worker correct; a multi-worker deploy (WORKERS>1) needs a shared store.
LOGIN_RATE_LIMIT_ATTEMPTS = int(os.environ.get("LOGIN_RATE_LIMIT_ATTEMPTS", "5"))
LOGIN_RATE_LIMIT_WINDOW_MINUTES = int(os.environ.get("LOGIN_RATE_LIMIT_WINDOW_MINUTES", "15"))
# Cookie flags. Dev over http on same-site localhost uses lax + non-secure; cross-site
# prod over https needs COOKIE_SAMESITE=none and COOKIE_SECURE=true.
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").strip().lower() in {"1", "true", "yes", "on"}
COOKIE_SAMESITE = os.environ.get("COOKIE_SAMESITE", "lax").strip().lower()
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

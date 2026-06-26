import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DATABASE_URL = os.environ["DATABASE_URL"]
# Connection-pool sizing (SQLAlchemy defaults 5 / 10). Raise for high concurrency, but keep
# WORKERS * (DB_POOL_SIZE + DB_MAX_OVERFLOW) under the database's max connections.
DB_POOL_SIZE = int(os.environ.get("DB_POOL_SIZE", "5"))
DB_MAX_OVERFLOW = int(os.environ.get("DB_MAX_OVERFLOW", "10"))
# Deployment environment. "production" turns on fail-fast config validation (see
# app/config_validation.py): the app refuses to boot with insecure defaults.
APP_ENV = os.environ.get("APP_ENV", "development").strip().lower()
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
# Comma-separated allowed origins. Whitespace around entries is stripped and blanks dropped,
# so "https://a.com, https://b.com" works (an un-stripped " https://b.com" would never match).
CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CORS_ORIGINS", "http://localhost:4200").split(",")
    if origin.strip()
]
# Max offers scored by the AI in parallel per match request. Each scoring is a slow
# LLM round-trip, so this bounds latency without overrunning provider rate limits.
# Defaults low to stay within free-tier provider limits (e.g. Gemini free tier allows
# only ~5-10 requests/minute); raise it via the env var on a paid tier with higher RPM.
AI_MATCH_CONCURRENCY = int(os.environ.get("AI_MATCH_CONCURRENCY", "3"))
# Client-side pacing (requests/minute) for Google/Gemini scoring calls, to stay under the
# free-tier per-minute cap (Gemini 2.5 Flash = 10 RPM, Flash-Lite = 30). Applied per user
# (each brings their own key/project). 0 disables pacing. OpenAI calls are not paced.
GOOGLE_RPM_LIMIT = int(os.environ.get("GOOGLE_RPM_LIMIT", "10"))

# --- Authentication ---
# Secret for signing session JWTs. MUST be overridden in production (a leaked or default
# secret lets anyone forge sessions). The dev default keeps local setup zero-config, and
# config_validation.py refuses to boot with it (or a too-short secret) when APP_ENV=production.
DEV_JWT_SECRET = "dev-insecure-change-me-0123456789abcdef"
# Minimum acceptable secret length (bytes) enforced in production.
MIN_JWT_SECRET_LENGTH = 32
JWT_SECRET = os.environ.get("JWT_SECRET", DEV_JWT_SECRET)
# Fernet secret encrypting users' stored provider API keys at rest. Unlike a password, an
# API key must be replayed to the provider, so it is symmetrically encrypted (never hashed)
# and the secret lives outside the DB. MUST be overridden in production; rotating it makes
# existing stored keys undecryptable. Generate one with:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
DEV_API_KEY_ENCRYPTION_KEY = "PG4EqSsP_M6JLdG-_C8nzuzDaj_JsdwAIY9v3ClP0lk="
API_KEY_ENCRYPTION_KEY = os.environ.get("API_KEY_ENCRYPTION_KEY", DEV_API_KEY_ENCRYPTION_KEY)
# Access tokens are short-lived; a long-lived refresh token (rotated + reuse-detected) is
# exchanged at /auth/refresh for a fresh access token, limiting how long a stolen access
# token stays usable. The refresh TTL also bounds the cookie lifetime.
ACCESS_TOKEN_TTL_MINUTES = int(os.environ.get("ACCESS_TOKEN_TTL_MINUTES", "15"))
REFRESH_TOKEN_TTL_DAYS = int(os.environ.get("REFRESH_TOKEN_TTL_DAYS", "14"))
# Login brute-force throttle: wrong-credential attempts allowed per (client IP, email)
# within the window before /auth/login returns 429. In-memory and per-process, so this is
# single-worker correct; a multi-worker deploy (WORKERS>1) needs a shared store.
LOGIN_RATE_LIMIT_ATTEMPTS = int(os.environ.get("LOGIN_RATE_LIMIT_ATTEMPTS", "5"))
LOGIN_RATE_LIMIT_WINDOW_MINUTES = int(os.environ.get("LOGIN_RATE_LIMIT_WINDOW_MINUTES", "15"))
# Rate-limiter backend: "memory" (default, per-process — correct only for a single worker)
# or "redis" (shared across workers/instances). "redis" needs REDIS_URL and the optional
# redis package (`uv sync --extra redis`); without it a multi-worker deploy throttles per
# worker. config_validation.py warns when WORKERS>1 with the memory backend.
RATE_LIMITER_BACKEND = os.environ.get("RATE_LIMITER_BACKEND", "memory").strip().lower()
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
# Cookie flags. Dev over http on same-site localhost uses lax + non-secure; cross-site
# prod over https needs COOKIE_SAMESITE=none and COOKIE_SECURE=true.
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").strip().lower() in {"1", "true", "yes", "on"}
COOKIE_SAMESITE = os.environ.get("COOKIE_SAMESITE", "lax").strip().lower()
# Network bind. Defaults to localhost so the API isn't reachable off-box; set
# HOST=0.0.0.0 explicitly (behind auth / a gateway) for container/remote deploys.
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))
# Number of worker processes. DB-backed state (model selection, usage, tokens) is shared,
# but the in-memory rate limiter + caches are per-process: for >1 worker set
# RATE_LIMITER_BACKEND=redis so login throttling stays correct across workers.
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

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

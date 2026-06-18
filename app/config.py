import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DATABASE_URL = os.environ["DATABASE_URL"]
USER_PROFILE_PATH = Path(__file__).resolve().parent.parent / "DATA" / "user_profile.md"
SCORING_AGENT_MODEL = os.environ.get("SCORING_AGENT_MODEL")

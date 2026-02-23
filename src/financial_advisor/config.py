"""Configuration: load .env secrets and user_profile.json into a Settings dataclass."""

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

DEFAULT_MAJOR_INDICES: dict[str, str] = {
    "^GSPC": "S&P 500",
    "^IXIC": "NASDAQ",
    "^DJI": "Dow Jones",
    "^VIX": "VIX",
}


@dataclass(frozen=True)
class Settings:
    # Secrets (from .env)
    telegram_bot_token: str
    anthropic_api_key: str
    allowed_user_ids: frozenset[int]

    # Briefing schedule
    briefing_hour: int = 7
    briefing_minute: int = 0

    # Claude model
    claude_model: str = "claude-haiku-4-5-20251001"

    # Logging
    log_level: str = "INFO"

    # User financial profile (from user_profile.json)
    user_profile: dict = field(default_factory=dict)

    # Market indices for briefing (symbol -> display name)
    major_indices: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_MAJOR_INDICES))

    # API backend URL (for bot → FastAPI communication)
    api_base_url: str = "http://localhost:8000"

    # V2: News & RAG
    finnhub_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    chromadb_path: Path = PROJECT_ROOT / "data" / "chromadb"
    news_fetch_interval_hours: int = 4

    # V2: Alerts
    alert_check_interval_minutes: int = 30

    # V2: Analysis model (Sonnet for recommendations, Haiku for chat)
    claude_model_analysis: str = "claude-sonnet-4-5-20250929"

    # Paths
    db_path: Path = PROJECT_ROOT / "data" / "conversations.db"


def load_settings(env_path: Path | None = None, profile_path: Path | None = None) -> Settings:
    """Load settings from .env and user_profile.json. Fails fast on missing required values."""
    env_file = env_path or PROJECT_ROOT / ".env"
    load_dotenv(env_file, override=True)

    # Required env vars
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    allowed_ids_raw = os.getenv("ALLOWED_TELEGRAM_USER_IDS", "")

    if not telegram_token:
        raise ValueError("TELEGRAM_BOT_TOKEN is required in .env")
    if not anthropic_key:
        raise ValueError("ANTHROPIC_API_KEY is required in .env")
    if not allowed_ids_raw.strip():
        raise ValueError("ALLOWED_TELEGRAM_USER_IDS is required in .env")

    allowed_user_ids = frozenset(
        int(uid.strip()) for uid in allowed_ids_raw.split(",") if uid.strip()
    )

    # Optional env vars
    briefing_hour = int(os.getenv("BRIEFING_HOUR", "7"))
    briefing_minute = int(os.getenv("BRIEFING_MINUTE", "0"))
    claude_model = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
    log_level = os.getenv("LOG_LEVEL", "INFO")

    # User profile (optional but recommended)
    profile_file = profile_path or PROJECT_ROOT / "config" / "user_profile.json"
    user_profile = {}
    if profile_file.exists():
        try:
            user_profile = json.loads(profile_file.read_text())
            logger.info("Loaded user profile from %s", profile_file)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load user profile: %s", e)
    else:
        logger.warning("No user profile found at %s — using defaults", profile_file)

    # Ensure data directory exists
    db_path = PROJECT_ROOT / "data" / "conversations.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Major indices: allow override from user_profile, else default
    major_indices = dict(DEFAULT_MAJOR_INDICES)
    if isinstance(user_profile.get("major_indices"), dict):
        major_indices = {str(k): str(v) for k, v in user_profile["major_indices"].items()}

    api_base_url = os.getenv("API_BASE_URL", "http://localhost:8000")

    # V2 settings
    finnhub_api_key = os.getenv("FINNHUB_API_KEY", "")
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    chromadb_path = PROJECT_ROOT / "data" / "chromadb"
    chromadb_path_raw = os.getenv("CHROMADB_PATH")
    if chromadb_path_raw:
        chromadb_path = Path(chromadb_path_raw)
        if not chromadb_path.is_absolute():
            chromadb_path = PROJECT_ROOT / chromadb_path
    news_fetch_interval_hours = int(os.getenv("NEWS_FETCH_INTERVAL_HOURS", "4"))
    alert_check_interval_minutes = int(os.getenv("ALERT_CHECK_INTERVAL_MINUTES", "30"))
    claude_model_analysis = os.getenv("CLAUDE_MODEL_ANALYSIS", "claude-sonnet-4-5-20250929")

    return Settings(
        telegram_bot_token=telegram_token,
        anthropic_api_key=anthropic_key,
        allowed_user_ids=allowed_user_ids,
        briefing_hour=briefing_hour,
        briefing_minute=briefing_minute,
        claude_model=claude_model,
        log_level=log_level,
        user_profile=user_profile,
        major_indices=major_indices,
        api_base_url=api_base_url,
        finnhub_api_key=finnhub_api_key,
        ollama_base_url=ollama_base_url,
        chromadb_path=chromadb_path,
        news_fetch_interval_hours=news_fetch_interval_hours,
        alert_check_interval_minutes=alert_check_interval_minutes,
        claude_model_analysis=claude_model_analysis,
        db_path=db_path,
    )

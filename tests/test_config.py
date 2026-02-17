"""Tests for config module."""

import json
from pathlib import Path

import pytest

from financial_advisor.config import load_settings


@pytest.fixture
def tmp_env(tmp_path: Path) -> Path:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "TELEGRAM_BOT_TOKEN=test-token-123\n"
        "ANTHROPIC_API_KEY=sk-ant-test-key\n"
        "ALLOWED_TELEGRAM_USER_IDS=111,222,333\n"
        "BRIEFING_HOUR=8\n"
        "BRIEFING_MINUTE=30\n"
        "CLAUDE_MODEL=claude-haiku-4-5-20251001\n"
        "LOG_LEVEL=DEBUG\n"
    )
    return env_file


@pytest.fixture
def tmp_profile(tmp_path: Path) -> Path:
    profile = {
        "name": "Test User",
        "risk_tolerance": "moderate",
        "holdings": [{"symbol": "AAPL", "shares": 10, "cost_basis": 150.0}],
        "watchlist": ["GOOGL"],
    }
    profile_file = tmp_path / "user_profile.json"
    profile_file.write_text(json.dumps(profile))
    return profile_file


def test_load_settings_basic(tmp_env: Path, tmp_profile: Path):
    settings = load_settings(env_path=tmp_env, profile_path=tmp_profile)

    assert settings.telegram_bot_token == "test-token-123"
    assert settings.anthropic_api_key == "sk-ant-test-key"
    assert settings.allowed_user_ids == frozenset({111, 222, 333})
    assert settings.briefing_hour == 8
    assert settings.briefing_minute == 30
    assert settings.claude_model == "claude-haiku-4-5-20251001"
    assert settings.log_level == "DEBUG"


def test_load_settings_with_profile(tmp_env: Path, tmp_profile: Path):
    settings = load_settings(env_path=tmp_env, profile_path=tmp_profile)
    assert settings.user_profile["name"] == "Test User"
    assert len(settings.user_profile["holdings"]) == 1
    assert settings.user_profile["holdings"][0]["symbol"] == "AAPL"


def test_load_settings_no_profile(tmp_env: Path, tmp_path: Path):
    missing = tmp_path / "nonexistent.json"
    settings = load_settings(env_path=tmp_env, profile_path=missing)
    assert settings.user_profile == {}


def test_load_settings_missing_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ALLOWED_TELEGRAM_USER_IDS", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ANTHROPIC_API_KEY=sk-ant-test\n"
        "ALLOWED_TELEGRAM_USER_IDS=111\n"
    )
    with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
        load_settings(env_path=env_file, profile_path=tmp_path / "nope.json")


def test_load_settings_missing_anthropic_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ALLOWED_TELEGRAM_USER_IDS", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "TELEGRAM_BOT_TOKEN=test-token\n"
        "ALLOWED_TELEGRAM_USER_IDS=111\n"
    )
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        load_settings(env_path=env_file, profile_path=tmp_path / "nope.json")


def test_load_settings_missing_user_ids(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ALLOWED_TELEGRAM_USER_IDS", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "TELEGRAM_BOT_TOKEN=test-token\n"
        "ANTHROPIC_API_KEY=sk-ant-test\n"
    )
    with pytest.raises(ValueError, match="ALLOWED_TELEGRAM_USER_IDS"):
        load_settings(env_path=env_file, profile_path=tmp_path / "nope.json")


def test_settings_is_frozen(tmp_env: Path, tmp_profile: Path):
    settings = load_settings(env_path=tmp_env, profile_path=tmp_profile)
    with pytest.raises(AttributeError):
        settings.telegram_bot_token = "new-token"

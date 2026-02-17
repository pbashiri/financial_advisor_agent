"""Shared pytest fixtures for integration tests."""

import os

import pytest

# Ensure required env vars exist so load_settings() works when api.app is imported
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test")
os.environ.setdefault("ALLOWED_TELEGRAM_USER_IDS", "1")

from financial_advisor.api.app import create_app
from financial_advisor.config import Settings


@pytest.fixture
def test_settings():
    """Minimal settings for API tests (no real secrets)."""
    return Settings(
        telegram_bot_token="test-token",
        anthropic_api_key="sk-test",
        allowed_user_ids=frozenset({1}),
        user_profile={},
        major_indices={"^GSPC": "S&P 500", "^VIX": "VIX"},
    )


@pytest.fixture
def test_app(test_settings, tmp_path):
    """FastAPI app with test storage and settings (no load_settings)."""
    db_path = tmp_path / "test_portfolio.db"
    return create_app(settings=test_settings, db_path=db_path)

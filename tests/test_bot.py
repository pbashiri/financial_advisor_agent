"""Tests for bot module (pure helpers and message splitting)."""

from financial_advisor.bot import _is_authorized, _split_message
from financial_advisor.config import Settings


def _make_settings(allowed_ids: set[int]) -> Settings:
    return Settings(
        telegram_bot_token="test",
        anthropic_api_key="sk-test",
        allowed_user_ids=frozenset(allowed_ids),
    )


def test_is_authorized_allowed():
    settings = _make_settings({111, 222})
    assert _is_authorized(111, settings) is True
    assert _is_authorized(222, settings) is True


def test_is_authorized_denied():
    settings = _make_settings({111})
    assert _is_authorized(222, settings) is False
    assert _is_authorized(0, settings) is False


def test_split_message_short():
    text = "Hello world"
    assert _split_message(text, 4096) == [text]


def test_split_message_exact_limit():
    text = "a" * 100
    assert _split_message(text, 100) == [text]


def test_split_message_splits_at_newline():
    line1 = "First line\n"
    line2 = "Second line\n"
    line3 = "Third"
    text = line1 + line2 + line3
    chunks = _split_message(text, limit=20)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert len(chunk) <= 20
    # Content is preserved (may lose newlines at split boundaries due to lstrip)
    assert "First" in chunks[0] and "Second" in chunks[1]


def test_split_message_long_without_newlines():
    text = "x" * 100
    chunks = _split_message(text, limit=30)
    assert len(chunks) >= 2
    assert "".join(chunks) == text


def test_split_message_empty():
    assert _split_message("", 100) == [""]

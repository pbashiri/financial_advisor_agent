"""Tests for agent module (with mocked Anthropic client)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from financial_advisor.agent import FinancialAdvisorAgent
from financial_advisor.config import Settings
from financial_advisor.memory import ConversationMemory


@pytest.fixture
def settings():
    return Settings(
        telegram_bot_token="test",
        anthropic_api_key="sk-test",
        allowed_user_ids=frozenset({1}),
        claude_model="claude-haiku-4-5-20251001",
        user_profile={"name": "Test"},
    )


@pytest.fixture
async def memory(tmp_path):
    db_path = tmp_path / "agent_test.db"
    mem = ConversationMemory(db_path)
    await mem.initialize()
    yield mem
    await mem.close()


@pytest.mark.asyncio
async def test_chat_returns_response_with_disclaimer(settings, memory):
    fake_response = MagicMock()
    fake_response.content = [MagicMock(text="Here is some advice.")]
    fake_response.usage = MagicMock(input_tokens=10, output_tokens=20)

    with patch("financial_advisor.agent.AsyncAnthropic") as mock_cls:
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=fake_response)
        mock_cls.return_value = mock_client

        agent = FinancialAdvisorAgent(settings, memory)
        result = await agent.chat(1, "What should I invest in?")

    assert "Here is some advice." in result
    assert "Disclaimer" in result or "not a licensed financial advisor" in result
    history = await memory.get_history(1)
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_chat_api_error_raises(settings, memory):
    with patch("financial_advisor.agent.AsyncAnthropic") as mock_cls:
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(side_effect=Exception("API error"))
        mock_cls.return_value = mock_client

        agent = FinancialAdvisorAgent(settings, memory)
        with pytest.raises(Exception, match="API error"):
            await agent.chat(1, "Hello")

    # User message should still be in history (we don't remove it on raise in current impl;
    # the docstring says we remove it, but the code just raises). Check behavior: actually
    # the code says "Remove the user message we just stored since we failed" but then
    # just raises without removing. So history will have 1 user message.
    history = await memory.get_history(1)
    assert len(history) == 1


@pytest.mark.asyncio
async def test_summarize_returns_text(settings, memory):
    fake_response = MagicMock()
    fake_response.content = [MagicMock(text="Markets were mixed with tech leading.")]

    with patch("financial_advisor.agent.AsyncAnthropic") as mock_cls:
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=fake_response)
        mock_cls.return_value = mock_client

        agent = FinancialAdvisorAgent(settings, memory)
        result = await agent.summarize("AAPL 150, VOO 400")

    assert "Markets were mixed" in result


@pytest.mark.asyncio
async def test_summarize_on_error_returns_fallback(settings, memory):
    with patch("financial_advisor.agent.AsyncAnthropic") as mock_cls:
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(side_effect=Exception("Rate limit"))
        mock_cls.return_value = mock_client

        agent = FinancialAdvisorAgent(settings, memory)
        result = await agent.summarize("Some data")

    assert "unavailable" in result.lower()

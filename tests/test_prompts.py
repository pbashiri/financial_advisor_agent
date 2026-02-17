"""Tests for prompts module."""

from financial_advisor.prompts import DISCLAIMER, build_system_prompt


def test_disclaimer_contains_key_phrases():
    assert "AI" in DISCLAIMER or "assistant" in DISCLAIMER
    assert "not a licensed financial advisor" in DISCLAIMER
    assert "informational" in DISCLAIMER
    assert "investment advice" in DISCLAIMER


def test_build_system_prompt_with_empty_profile():
    prompt = build_system_prompt({})
    assert "financial advisor" in prompt.lower()
    assert "No client profile" in prompt or "profile" in prompt.lower()
    assert "IMPORTANT RULES" in prompt
    assert "FORMATTING" in prompt


def test_build_system_prompt_with_profile():
    profile = {
        "name": "Test User",
        "risk_tolerance": "moderate",
        "holdings": [{"symbol": "AAPL", "shares": 10}],
    }
    prompt = build_system_prompt(profile)
    assert "client's financial profile" in prompt or "financial profile" in prompt
    assert "Test User" in prompt
    assert "AAPL" in prompt
    assert "moderate" in prompt


def test_build_system_prompt_guardrails_present():
    prompt = build_system_prompt({"name": "X"})
    assert "cryptocurrencies" in prompt or "meme" in prompt or "day trading" in prompt
    assert "disclaimer" in prompt.lower()
    assert "risk" in prompt.lower()

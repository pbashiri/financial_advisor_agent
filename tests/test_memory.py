"""Tests for conversation memory module."""

from pathlib import Path

import pytest

from financial_advisor.memory import MAX_HISTORY, ConversationMemory


@pytest.fixture
async def memory(tmp_path: Path):
    db_path = tmp_path / "test.db"
    mem = ConversationMemory(db_path)
    await mem.initialize()
    yield mem
    await mem.close()


async def test_add_and_get_message(memory: ConversationMemory):
    await memory.add_message(1, "user", "Hello")
    await memory.add_message(1, "assistant", "Hi there!")

    history = await memory.get_history(1)
    assert len(history) == 2
    assert history[0] == {"role": "user", "content": "Hello"}
    assert history[1] == {"role": "assistant", "content": "Hi there!"}


async def test_separate_user_histories(memory: ConversationMemory):
    await memory.add_message(1, "user", "User 1 message")
    await memory.add_message(2, "user", "User 2 message")

    history1 = await memory.get_history(1)
    history2 = await memory.get_history(2)

    assert len(history1) == 1
    assert len(history2) == 1
    assert history1[0]["content"] == "User 1 message"
    assert history2[0]["content"] == "User 2 message"


async def test_clear_history(memory: ConversationMemory):
    await memory.add_message(1, "user", "Hello")
    await memory.add_message(1, "assistant", "Hi!")

    deleted = await memory.clear_history(1)
    assert deleted == 2

    history = await memory.get_history(1)
    assert len(history) == 0


async def test_clear_only_target_user(memory: ConversationMemory):
    await memory.add_message(1, "user", "User 1")
    await memory.add_message(2, "user", "User 2")

    await memory.clear_history(1)

    assert len(await memory.get_history(1)) == 0
    assert len(await memory.get_history(2)) == 1


async def test_sliding_window_prunes(memory: ConversationMemory):
    # Add more than MAX_HISTORY messages
    for i in range(MAX_HISTORY + 10):
        await memory.add_message(1, "user", f"Message {i}")

    history = await memory.get_history(1)
    assert len(history) == MAX_HISTORY
    # Should have the latest messages, not the earliest
    assert history[0]["content"] == "Message 10"
    assert history[-1]["content"] == f"Message {MAX_HISTORY + 9}"


async def test_empty_history(memory: ConversationMemory):
    history = await memory.get_history(999)
    assert history == []


async def test_token_estimate_stored(memory: ConversationMemory):
    await memory.add_message(1, "assistant", "Response", token_estimate=150)
    # Verify message was stored (token_estimate is metadata, not returned in get_history)
    history = await memory.get_history(1)
    assert len(history) == 1
    assert history[0]["content"] == "Response"

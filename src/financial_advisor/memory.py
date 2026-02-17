"""Async SQLite conversation storage with sliding window."""

import logging
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

MAX_HISTORY = 50  # messages per user


class ConversationMemory:
    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """Create the database and conversations table if they don't exist."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                token_estimate INTEGER DEFAULT 0
            )
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversations_user
            ON conversations(user_id, id)
        """)
        await self._db.commit()
        logger.info("Conversation memory initialized at %s", self._db_path)

    async def add_message(
        self, user_id: int, role: str, content: str, token_estimate: int = 0
    ) -> None:
        """Store a message and prune old messages beyond the sliding window."""
        assert self._db is not None, "Call initialize() first"
        await self._db.execute(
            "INSERT INTO conversations (user_id, role, content, token_estimate)"
            " VALUES (?, ?, ?, ?)",
            (user_id, role, content, token_estimate),
        )
        # Prune: keep only the last MAX_HISTORY messages per user
        await self._db.execute(
            """
            DELETE FROM conversations
            WHERE user_id = ? AND id NOT IN (
                SELECT id FROM conversations
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT ?
            )
            """,
            (user_id, user_id, MAX_HISTORY),
        )
        await self._db.commit()

    async def get_history(self, user_id: int) -> list[dict]:
        """Return conversation history as a list of {"role": ..., "content": ...} dicts."""
        assert self._db is not None, "Call initialize() first"
        cursor = await self._db.execute(
            """
            SELECT role, content FROM conversations
            WHERE user_id = ?
            ORDER BY id ASC
            """,
            (user_id,),
        )
        rows = await cursor.fetchall()
        return [{"role": role, "content": content} for role, content in rows]

    async def clear_history(self, user_id: int) -> int:
        """Delete all messages for a user. Returns the number of deleted messages."""
        assert self._db is not None, "Call initialize() first"
        cursor = await self._db.execute(
            "DELETE FROM conversations WHERE user_id = ?",
            (user_id,),
        )
        await self._db.commit()
        return cursor.rowcount

    async def close(self) -> None:
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None

"""Async SQLite CRUD for portfolio holdings and transactions."""

import logging
from pathlib import Path

import aiosqlite

from .models import Holding, Transaction

logger = logging.getLogger(__name__)


class PortfolioStorage:
    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """Create portfolio tables if they don't exist."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS holdings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL UNIQUE,
                shares REAL NOT NULL,
                cost_basis REAL NOT NULL,
                account_type TEXT DEFAULT 'brokerage',
                notes TEXT,
                added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                action TEXT NOT NULL CHECK(action IN ('BUY','SELL')),
                shares REAL NOT NULL,
                price REAL NOT NULL,
                fees REAL DEFAULT 0,
                transacted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                notes TEXT
            )
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_transactions_symbol
            ON transactions(symbol)
        """)
        await self._db.commit()
        logger.info("Portfolio storage initialized at %s", self._db_path)

    async def seed_from_profile(self, holdings_data: list[dict]) -> int:
        """Seed holdings from user_profile.json if the table is empty. Returns count inserted."""
        assert self._db is not None, "Call initialize() first"
        cursor = await self._db.execute("SELECT COUNT(*) FROM holdings")
        (count,) = await cursor.fetchone()
        if count > 0:
            return 0

        inserted = 0
        for h in holdings_data:
            symbol = h.get("symbol", "").strip().upper()
            shares = h.get("shares", 0)
            cost_basis = h.get("cost_basis", 0)
            if not symbol or shares <= 0 or cost_basis <= 0:
                continue
            await self._db.execute(
                """
                INSERT OR IGNORE INTO holdings (symbol, shares, cost_basis, account_type, notes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (symbol, shares, cost_basis, h.get("account_type", "brokerage"), h.get("notes")),
            )
            inserted += 1
        await self._db.commit()
        logger.info("Seeded %d holdings from user profile", inserted)
        return inserted

    async def get_holdings(self) -> list[Holding]:
        """Return all holdings ordered by symbol."""
        assert self._db is not None, "Call initialize() first"
        cursor = await self._db.execute(
            "SELECT symbol, shares, cost_basis, account_type, notes, added_at, updated_at "
            "FROM holdings ORDER BY symbol"
        )
        rows = await cursor.fetchall()
        return [Holding(**dict(row)) for row in rows]

    async def upsert_holding(self, holding: Holding) -> None:
        """Insert or update a holding by symbol."""
        assert self._db is not None, "Call initialize() first"
        await self._db.execute(
            """
            INSERT INTO holdings (symbol, shares, cost_basis, account_type, notes, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(symbol) DO UPDATE SET
                shares = excluded.shares,
                cost_basis = excluded.cost_basis,
                account_type = excluded.account_type,
                notes = excluded.notes,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                holding.symbol,
                holding.shares,
                holding.cost_basis,
                holding.account_type,
                holding.notes,
            ),
        )
        await self._db.commit()

    async def delete_holding(self, symbol: str) -> bool:
        """Delete a holding by symbol. Returns True if deleted."""
        assert self._db is not None, "Call initialize() first"
        cursor = await self._db.execute("DELETE FROM holdings WHERE symbol = ?", (symbol.upper(),))
        await self._db.commit()
        return cursor.rowcount > 0

    async def add_transaction(self, tx: Transaction) -> None:
        """Record a transaction."""
        assert self._db is not None, "Call initialize() first"
        await self._db.execute(
            """
            INSERT INTO transactions (symbol, action, shares, price, fees, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (tx.symbol, tx.action, tx.shares, tx.price, tx.fees, tx.notes),
        )
        await self._db.commit()

    async def get_transactions(self, symbol: str | None = None) -> list[Transaction]:
        """Return transactions, optionally filtered by symbol."""
        assert self._db is not None, "Call initialize() first"
        if symbol:
            cursor = await self._db.execute(
                "SELECT symbol, action, shares, price, fees, transacted_at, notes "
                "FROM transactions WHERE symbol = ? ORDER BY transacted_at DESC",
                (symbol.upper(),),
            )
        else:
            cursor = await self._db.execute(
                "SELECT symbol, action, shares, price, fees, transacted_at, notes "
                "FROM transactions ORDER BY transacted_at DESC"
            )
        rows = await cursor.fetchall()
        return [Transaction(**dict(row)) for row in rows]

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

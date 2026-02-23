"""Async SQLite CRUD for alert configs and triggered alert history."""

import logging
from datetime import datetime
from pathlib import Path

import aiosqlite

from .models import Alert, AlertConfig, AlertType

logger = logging.getLogger(__name__)


class AlertStorage:
    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """Create alert tables if they don't exist."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)

        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS alert_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_type TEXT NOT NULL,
                symbol TEXT,
                threshold REAL NOT NULL,
                enabled INTEGER DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                notes TEXT DEFAULT ''
            )
        """)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS alert_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                config_id INTEGER NOT NULL REFERENCES alert_configs(id),
                triggered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                message TEXT NOT NULL,
                acknowledged INTEGER DEFAULT 0,
                acknowledged_at DATETIME
            )
        """)
        await self._db.commit()
        logger.info("Alert storage initialized at %s", self._db_path)

    async def add_config(self, config: AlertConfig) -> int:
        """Insert a new alert config. Returns the new config ID."""
        assert self._db is not None, "Call initialize() first"
        cursor = await self._db.execute(
            """
            INSERT INTO alert_configs (alert_type, symbol, threshold, enabled, notes)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                config.alert_type.value,
                config.symbol,
                config.threshold,
                config.enabled,
                config.notes,
            ),
        )
        await self._db.commit()
        return cursor.lastrowid

    async def get_configs(self, enabled_only: bool = False) -> list[AlertConfig]:
        """Return all alert configs, optionally only enabled ones."""
        assert self._db is not None, "Call initialize() first"
        query = (
            "SELECT id, alert_type, symbol, threshold, enabled, created_at, notes"
            " FROM alert_configs"
        )
        if enabled_only:
            query += " WHERE enabled = 1"
        query += " ORDER BY id"

        self._db.row_factory = aiosqlite.Row
        cursor = await self._db.execute(query)
        rows = await cursor.fetchall()
        return [
            AlertConfig(
                id=row["id"],
                alert_type=AlertType(row["alert_type"]),
                symbol=row["symbol"],
                threshold=row["threshold"],
                enabled=bool(row["enabled"]),
                created_at=row["created_at"],
                notes=row["notes"] or "",
            )
            for row in rows
        ]

    async def remove_config(self, config_id: int) -> bool:
        """Delete an alert config by ID. Returns True if deleted."""
        assert self._db is not None, "Call initialize() first"
        cursor = await self._db.execute("DELETE FROM alert_configs WHERE id = ?", (config_id,))
        await self._db.commit()
        return cursor.rowcount > 0

    async def toggle_config(self, config_id: int, enabled: bool) -> bool:
        """Enable or disable an alert config. Returns True if updated."""
        assert self._db is not None, "Call initialize() first"
        cursor = await self._db.execute(
            "UPDATE alert_configs SET enabled = ? WHERE id = ?",
            (int(enabled), config_id),
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def record_alert(self, alert: Alert) -> int:
        """Record a triggered alert. Returns the alert history ID."""
        assert self._db is not None, "Call initialize() first"
        cursor = await self._db.execute(
            """
            INSERT INTO alert_history (config_id, triggered_at, message, acknowledged)
            VALUES (?, ?, ?, ?)
            """,
            (
                alert.config_id,
                alert.triggered_at.isoformat(),
                alert.message,
                int(alert.acknowledged),
            ),
        )
        await self._db.commit()
        return cursor.lastrowid

    async def acknowledge_alert(self, alert_id: int) -> bool:
        """Mark an alert as acknowledged. Returns True if updated."""
        assert self._db is not None, "Call initialize() first"
        cursor = await self._db.execute(
            "UPDATE alert_history SET acknowledged = 1, acknowledged_at = ? WHERE id = ?",
            (datetime.now().isoformat(), alert_id),
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def was_recently_triggered(self, config_id: int, hours: int = 24) -> bool:
        """Check if an alert config was triggered within the last N hours (dedup)."""
        assert self._db is not None, "Call initialize() first"
        cursor = await self._db.execute(
            """
            SELECT COUNT(*) FROM alert_history
            WHERE config_id = ?
            AND triggered_at > datetime('now', ?)
            """,
            (config_id, f"-{hours} hours"),
        )
        (count,) = await cursor.fetchone()
        return count > 0

    async def get_recent_alerts(self, hours: int = 24) -> list[Alert]:
        """Get alerts triggered in the last N hours."""
        assert self._db is not None, "Call initialize() first"
        self._db.row_factory = aiosqlite.Row
        cursor = await self._db.execute(
            """
            SELECT id, config_id, triggered_at, message, acknowledged, acknowledged_at
            FROM alert_history
            WHERE triggered_at > datetime('now', ?)
            ORDER BY triggered_at DESC
            """,
            (f"-{hours} hours",),
        )
        rows = await cursor.fetchall()
        return [
            Alert(
                id=row["id"],
                config_id=row["config_id"],
                triggered_at=row["triggered_at"],
                message=row["message"],
                acknowledged=bool(row["acknowledged"]),
                acknowledged_at=row["acknowledged_at"],
            )
            for row in rows
        ]

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

"""
Alert event + utilization-history auto-cleanup.

Runs once per day. Deletes resolved alert_events and subnet_utilization_history
rows older than the configured retention windows (defaults: 90 days for
alert events, 30 days for utilization history).
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

import aiosqlite

from app.config import get_settings

log = logging.getLogger("pktipam.cleanup")
settings = get_settings()

_CLEANUP_INTERVAL = 86_400  # once per day


class AlertCleanup:
    _instance: "Optional[AlertCleanup]" = None

    def __init__(self, interval_seconds: int = _CLEANUP_INTERVAL):
        self._interval = interval_seconds
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        AlertCleanup._instance = self
        self._task = asyncio.create_task(self._run_loop())
        log.info(f"Alert cleanup started (interval={self._interval}s)")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run_loop(self) -> None:
        while True:
            try:
                await self._cleanup()
            except Exception as e:
                log.error(f"Alert cleanup error: {e}")
            await asyncio.sleep(self._interval)

    async def run_once(self) -> dict:
        """Run cleanup immediately and return what it did — used by the
        Settings -> Data -> Storage "Run cleanup now" button."""
        return await self._cleanup()

    async def _cleanup(self) -> dict:
        db_path = settings.db_path
        async with aiosqlite.connect(db_path) as db:
            async def _setting(key: str, default: int) -> int:
                async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cur:
                    row = await cur.fetchone()
                if not row:
                    return default
                try:
                    return int(json.loads(row[0]))
                except (ValueError, TypeError):
                    return default

            alert_retention_days = await _setting("alert_event_retention_days", 90)
            util_retention_days = await _setting("utilization_history_retention_days", 30)

            result = await db.execute(
                "DELETE FROM alert_events WHERE resolved = 1 AND created_at < datetime('now', ?)",
                (f"-{alert_retention_days} days",),
            )
            alerts_deleted = result.rowcount

            result = await db.execute(
                "DELETE FROM subnet_utilization_history WHERE recorded_at < datetime('now', ?)",
                (f"-{util_retention_days} days",),
            )
            util_deleted = result.rowcount

            await db.commit()

        if alerts_deleted or util_deleted:
            log.info(
                f"Cleanup: removed {alerts_deleted} resolved alerts (>{alert_retention_days}d), "
                f"{util_deleted} subnet_utilization_history rows (>{util_retention_days}d)"
            )
        return {
            "status": "ok",
            "alert_events_deleted": alerts_deleted,
            "utilization_history_deleted": util_deleted,
            "alert_retention_days": alert_retention_days,
            "utilization_retention_days": util_retention_days,
        }

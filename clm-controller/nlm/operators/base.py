"""NLM Operator Base — abstract async operator with lifecycle management."""
from __future__ import annotations

import abc
import asyncio
import logging
import traceback
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("nlm.operators")


class Operator(abc.ABC):
    """Abstract base for all NLM operators.

    Each operator runs a periodic loop that calls `run_once()` at a
    configurable interval.  The loop is managed as an asyncio background
    task so it integrates cleanly with the FastAPI event loop.
    """

    def __init__(self, interval: int = 60) -> None:
        self.interval = interval
        self._task: asyncio.Task | None = None
        self._running = False
        self._enabled = True
        self._last_run: datetime | None = None
        self._last_result: dict[str, Any] = {}
        self._run_count = 0
        self._error_count = 0
        self._last_error: str = ""

    # ── Abstract ──────────────────────────────────────────────────

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Unique operator name (e.g. 'reconciler')."""
        ...

    @abc.abstractmethod
    async def run_once(self) -> dict[str, Any]:
        """Execute a single iteration of the operator's logic.

        Returns a dict summarising what happened (for status/logging).
        """
        ...

    # ── Lifecycle ─────────────────────────────────────────────────

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name=f"op-{self.name}")
        logger.info("Operator started: %s (interval=%ds)", self.name, self.interval)

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Operator stopped: %s", self.name)

    async def trigger(self) -> dict[str, Any]:
        """Manually trigger a single tick (for API/testing)."""
        return await self._tick()

    def toggle(self, enabled: bool) -> None:
        self._enabled = enabled
        state = "enabled" if enabled else "disabled"
        logger.info("Operator %s: %s", self.name, state)

    # ── Status ────────────────────────────────────────────────────

    def status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "running": self._running,
            "enabled": self._enabled,
            "interval_seconds": self.interval,
            "run_count": self._run_count,
            "error_count": self._error_count,
            "last_run": self._last_run.isoformat() if self._last_run else None,
            "last_result": self._last_result,
            "last_error": self._last_error,
        }

    # ── Internal ──────────────────────────────────────────────────

    async def _loop(self) -> None:
        while self._running:
            if self._enabled:
                await self._tick()
            try:
                await asyncio.sleep(self.interval)
            except asyncio.CancelledError:
                break

    async def _tick(self) -> dict[str, Any]:
        try:
            result = await self.run_once()
            self._run_count += 1
            self._last_run = datetime.now(timezone.utc)
            self._last_result = result
            self._last_error = ""
            return result
        except Exception as exc:
            self._error_count += 1
            self._last_error = f"{exc.__class__.__name__}: {exc}"
            logger.error("Operator %s error: %s\n%s",
                         self.name, exc, traceback.format_exc())
            return {"error": str(exc)}

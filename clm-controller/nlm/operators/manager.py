"""NLM Operator Manager — lifecycle coordinator for all operators."""
from __future__ import annotations

import logging
from typing import Any

from .base import Operator

logger = logging.getLogger("nlm.operators")


class OperatorManager:
    """Manages registration, startup, shutdown, and status of all operators."""

    def __init__(self) -> None:
        self.operators: dict[str, Operator] = {}

    def register(self, op: Operator) -> None:
        self.operators[op.name] = op
        logger.info("Operator registered: %s", op.name)

    async def start_all(self) -> None:
        logger.info("Starting %d operators", len(self.operators))
        for op in self.operators.values():
            await op.start()

    async def stop_all(self) -> None:
        logger.info("Stopping %d operators", len(self.operators))
        for op in self.operators.values():
            await op.stop()

    def get(self, name: str) -> Operator | None:
        return self.operators.get(name)

    def status(self) -> dict[str, Any]:
        return {
            "operator_count": len(self.operators),
            "operators": {
                name: op.status() for name, op in self.operators.items()
            },
        }

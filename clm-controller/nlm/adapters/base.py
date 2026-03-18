"""
NLM Backend Adapter — Abstract Base Class
==========================================
All backend adapters must implement this interface.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class BackendResult:
    """Result of a backend operation."""
    success: bool = True
    message: str = ""
    data: dict[str, Any] | None = None
    error: str = ""


class NodeBackend(abc.ABC):
    """Abstract interface for infrastructure backends."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    @abc.abstractmethod
    def list_nodes(self) -> list[dict[str, Any]]:
        """List all nodes managed by this backend."""
        ...

    @abc.abstractmethod
    def get_node(self, node_id: str) -> dict[str, Any]:
        """Get details of a specific node."""
        ...

    @abc.abstractmethod
    def cordon(self, node_id: str, reason: str) -> BackendResult:
        """Cordon/disable scheduling on a node."""
        ...

    @abc.abstractmethod
    def uncordon(self, node_id: str) -> BackendResult:
        """Uncordon/re-enable scheduling on a node."""
        ...

    @abc.abstractmethod
    def drain(self, node_id: str, grace_period_seconds: int = 300) -> BackendResult:
        """Drain workloads from a node."""
        ...

    @abc.abstractmethod
    def reboot(self, node_id: str) -> BackendResult:
        """Reboot a node."""
        ...

    @abc.abstractmethod
    def reimage(self, node_id: str, image: str = "") -> BackendResult:
        """Re-image/re-provision a node."""
        ...

    @abc.abstractmethod
    def get_status(self, node_id: str) -> str:
        """Get the backend-native status of a node."""
        ...

    @abc.abstractmethod
    def set_metadata(self, node_id: str, key: str, value: str) -> BackendResult:
        """Set a metadata key/value on a node."""
        ...

    @abc.abstractmethod
    def exec_command(self, node_id: str, command: str) -> BackendResult:
        """Execute a command on a node."""
        ...

    def get_gpu_info(self, node_id: str) -> dict[str, Any]:
        """Get GPU information from a node."""
        result = self.exec_command(
            node_id,
            "nvidia-smi --query-gpu=name,memory.total,driver_version,temperature.gpu,"
            "ecc.errors.uncorrected.volatile.total --format=csv,noheader,nounits",
        )
        if not result.success:
            return {"error": result.error}

        lines = (result.data or {}).get("stdout", "").strip().split("\n")
        gpus = []
        for line in lines:
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 5:
                gpus.append({
                    "name": parts[0],
                    "memory_mb": parts[1],
                    "driver_version": parts[2],
                    "temperature_c": parts[3],
                    "ecc_uncorrectable": parts[4],
                })
        return {"gpu_count": len(gpus), "gpus": gpus}

"""
NLM Backend Adapter — NVIDIA BCM (Base Command Manager)
=======================================================
All operations are cmsh-native. No direct SSH to compute nodes.
Commands are executed via the BCM head node.
"""

from __future__ import annotations

import logging
import subprocess
from typing import Any

from nlm.adapters.base import BackendResult, NodeBackend

logger = logging.getLogger(__name__)


class BCMAdapter(NodeBackend):
    """
    BCM backend adapter using cmsh (Base Command Manager shell).

    All node operations are performed through the BCM head node
    via cmsh commands, following the BCM operational model.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.cmsh_bin = config.get("cmsh_bin", "/usr/bin/cmsh")
        self.headnode = config.get("headnode", "localhost")
        self.ssh_key = config.get("ssh_key", "")
        self.timeout = config.get("timeout_seconds", 30)

    def _run_cmsh(self, command: str) -> BackendResult:
        """Execute a cmsh command, optionally via SSH to the head node."""
        full_cmd = f'{self.cmsh_bin} -c "{command}"'

        if self.headnode and self.headnode != "localhost":
            ssh_opts = f"-i {self.ssh_key}" if self.ssh_key else ""
            full_cmd = f"ssh {ssh_opts} {self.headnode} {full_cmd}"

        logger.debug("BCM exec: %s", full_cmd)

        try:
            result = subprocess.run(
                full_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            if result.returncode != 0:
                return BackendResult(
                    success=False,
                    error=result.stderr.strip(),
                    data={"stdout": result.stdout, "stderr": result.stderr},
                )
            return BackendResult(
                success=True,
                message=result.stdout.strip(),
                data={"stdout": result.stdout},
            )
        except subprocess.TimeoutExpired:
            return BackendResult(success=False, error=f"cmsh timeout ({self.timeout}s)")
        except Exception as exc:
            return BackendResult(success=False, error=str(exc))

    def list_nodes(self) -> list[dict[str, Any]]:
        """List all compute nodes from BCM."""
        result = self._run_cmsh("device; list")
        if not result.success:
            logger.error("Failed to list BCM nodes: %s", result.error)
            return []

        nodes = []
        for line in (result.data or {}).get("stdout", "").split("\n"):
            line = line.strip()
            if not line or line.startswith("Name"):
                continue
            parts = line.split()
            if len(parts) >= 1:
                nodes.append({
                    "id": parts[0],
                    "backend": "bcm",
                    "raw": line,
                })
        return nodes

    def get_node(self, node_id: str) -> dict[str, Any]:
        """Get BCM device details."""
        cmds = [
            f"device; use {node_id}; get status",
            f"device; use {node_id}; get category",
            f"device; use {node_id}; get ip",
            f"device; use {node_id}; get mac",
            f"device; use {node_id}; get notes",
        ]
        info: dict[str, Any] = {"id": node_id, "backend": "bcm"}
        for cmd in cmds:
            result = self._run_cmsh(cmd)
            if result.success:
                key = cmd.split("get ")[-1]
                info[key] = result.message
        return info

    def cordon(self, node_id: str, reason: str) -> BackendResult:
        """Drain a node in BCM (cordon equivalent)."""
        cmd = (
            f"device; use {node_id}; "
            f"set status DRAINED; "
            f"set drainstatus '{reason}'; "
            f"set notes 'NLM: cordoned — {reason}'; "
            f"commit"
        )
        result = self._run_cmsh(cmd)
        if result.success:
            logger.info("BCM cordon: %s — %s", node_id, reason)
        return result

    def uncordon(self, node_id: str) -> BackendResult:
        """Set node status to UP in BCM (uncordon equivalent)."""
        cmd = (
            f"device; use {node_id}; "
            f"set status UP; "
            f"set drainstatus ''; "
            f"set notes 'NLM: uncordoned'; "
            f"commit"
        )
        result = self._run_cmsh(cmd)
        if result.success:
            logger.info("BCM uncordon: %s", node_id)
        return result

    def drain(self, node_id: str, grace_period_seconds: int = 300) -> BackendResult:
        """Drain Slurm jobs + BCM status."""
        # First drain Slurm
        slurm_cmd = f"device; use {node_id}; exec 'scontrol update NodeName={node_id} State=drain Reason=\"NLM maintenance\"'"
        self._run_cmsh(slurm_cmd)

        # Then set BCM status
        return self.cordon(node_id, "drain:nlm-maintenance")

    def reboot(self, node_id: str) -> BackendResult:
        """Power cycle a node via BCM."""
        cmd = f"device; use {node_id}; power reset; commit"
        result = self._run_cmsh(cmd)
        if result.success:
            logger.info("BCM reboot: %s", node_id)
        return result

    def reimage(self, node_id: str, image: str = "") -> BackendResult:
        """Re-image a node via BCM imagenode."""
        img_opt = f"set softwareimage {image}; " if image else ""
        cmd = f"device; use {node_id}; {img_opt}imagenode; commit"
        result = self._run_cmsh(cmd)
        if result.success:
            logger.info("BCM reimage: %s (image=%s)", node_id, image or "default")
        return result

    def get_status(self, node_id: str) -> str:
        """Get the BCM status of a node."""
        result = self._run_cmsh(f"device; use {node_id}; get status")
        return result.message if result.success else "UNKNOWN"

    def set_metadata(self, node_id: str, key: str, value: str) -> BackendResult:
        """Set a note/tag on a BCM device."""
        cmd = f"device; use {node_id}; set notes '{key}={value}'; commit"
        return self._run_cmsh(cmd)

    def exec_command(self, node_id: str, command: str) -> BackendResult:
        """Execute a command on a node via BCM exec."""
        cmd = f"device; use {node_id}; exec '{command}'"
        return self._run_cmsh(cmd)

    # ── BCM-specific operations ──────────────────────────────────────

    def get_allocation(self, node_id: str) -> str:
        """Check if a node has an active BCM allocation (customer assignment)."""
        result = self._run_cmsh(f"device; use {node_id}; get allocation")
        alloc = result.message.strip() if result.success else ""
        if alloc and alloc not in ("none", "(null)", ""):
            return alloc
        return ""

    def set_category(self, node_id: str, category: str) -> BackendResult:
        """Set the BCM category (node group) for a node."""
        cmd = f"device; use {node_id}; set category {category}; commit"
        return self._run_cmsh(cmd)

    def get_slurm_state(self, node_id: str) -> str:
        """Get Slurm node state."""
        result = self._run_cmsh(
            f"device; use {node_id}; exec 'scontrol show node {node_id}'"
        )
        if result.success:
            for line in result.message.split():
                if line.startswith("State="):
                    return line.split("=", 1)[1]
        return "UNKNOWN"

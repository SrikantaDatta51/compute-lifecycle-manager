"""
NLM Backend Adapter — Canonical MAAS
=====================================
Uses the MAAS REST API (v2.0) for bare metal lifecycle management.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from nlm.adapters.base import BackendResult, NodeBackend

logger = logging.getLogger(__name__)


class MAASAdapter(NodeBackend):
    """
    Canonical MAAS backend adapter.

    Uses MAAS REST API v2.0 for machine lifecycle operations:
    commission → deploy → release → lock/unlock.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.api_url = config.get("api_url", "http://localhost:5240/MAAS/api/2.0")
        self.api_key = config.get("api_key", "")
        self.timeout = config.get("timeout_seconds", 30)

    def _request(
        self,
        endpoint: str,
        method: str = "GET",
        data: dict[str, Any] | None = None,
    ) -> BackendResult:
        """Make an authenticated MAAS API request."""
        url = urljoin(self.api_url + "/", endpoint)
        headers = {
            "Authorization": f"OAuth oauth_token={self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            body = json.dumps(data).encode() if data else None
            req = Request(url, data=body, headers=headers, method=method)
            with urlopen(req, timeout=self.timeout) as resp:
                resp_data = json.loads(resp.read().decode())
                return BackendResult(
                    success=True,
                    message=f"{method} {endpoint} → {resp.status}",
                    data=resp_data if isinstance(resp_data, dict) else {"result": resp_data},
                )
        except Exception as exc:
            return BackendResult(success=False, error=str(exc))

    def _get_system_id(self, node_id: str) -> str:
        """Resolve a hostname to a MAAS system_id."""
        result = self._request(f"machines/?hostname={node_id}")
        if result.success and result.data:
            machines = result.data.get("result", [])
            if isinstance(machines, list) and machines:
                return machines[0].get("system_id", "")
        return node_id  # Fallback: assume node_id is system_id

    def list_nodes(self) -> list[dict[str, Any]]:
        """List all MAAS machines."""
        result = self._request("machines/")
        if not result.success:
            logger.error("Failed to list MAAS machines: %s", result.error)
            return []

        machines = result.data.get("result", []) if result.data else []
        if not isinstance(machines, list):
            return []

        return [
            {
                "id": m.get("hostname", m.get("system_id", "")),
                "system_id": m.get("system_id", ""),
                "status_name": m.get("status_name", ""),
                "power_state": m.get("power_state", ""),
                "zone": m.get("zone", {}).get("name", ""),
                "pool": m.get("pool", {}).get("name", ""),
                "backend": "maas",
            }
            for m in machines
        ]

    def get_node(self, node_id: str) -> dict[str, Any]:
        """Get MAAS machine details."""
        sys_id = self._get_system_id(node_id)
        result = self._request(f"machines/{sys_id}/")
        if result.success and result.data:
            return {**result.data, "backend": "maas"}
        return {"id": node_id, "error": result.error, "backend": "maas"}

    def cordon(self, node_id: str, reason: str) -> BackendResult:
        """Lock a MAAS machine (cordon equivalent)."""
        sys_id = self._get_system_id(node_id)
        result = self._request(
            f"machines/{sys_id}/?op=lock",
            method="POST",
            data={"comment": f"NLM: {reason}"},
        )
        if result.success:
            logger.info("MAAS lock: %s — %s", node_id, reason)
        return result

    def uncordon(self, node_id: str) -> BackendResult:
        """Unlock a MAAS machine (uncordon equivalent)."""
        sys_id = self._get_system_id(node_id)
        result = self._request(f"machines/{sys_id}/?op=unlock", method="POST")
        if result.success:
            logger.info("MAAS unlock: %s", node_id)
        return result

    def drain(self, node_id: str, grace_period_seconds: int = 300) -> BackendResult:
        """Release a MAAS machine (drain equivalent)."""
        sys_id = self._get_system_id(node_id)
        result = self._request(
            f"machines/{sys_id}/?op=release",
            method="POST",
            data={"comment": "NLM: drain for maintenance"},
        )
        if result.success:
            logger.info("MAAS release (drain): %s", node_id)
        return result

    def reboot(self, node_id: str) -> BackendResult:
        """Power cycle a MAAS machine."""
        sys_id = self._get_system_id(node_id)
        # Power off then on
        self._request(f"machines/{sys_id}/?op=power_off", method="POST")
        result = self._request(f"machines/{sys_id}/?op=power_on", method="POST")
        if result.success:
            logger.info("MAAS reboot: %s", node_id)
        return result

    def reimage(self, node_id: str, image: str = "") -> BackendResult:
        """Deploy (reimage) a MAAS machine."""
        sys_id = self._get_system_id(node_id)
        deploy_data: dict[str, Any] = {}
        if image:
            deploy_data["distro_series"] = image

        result = self._request(
            f"machines/{sys_id}/?op=deploy",
            method="POST",
            data=deploy_data,
        )
        if result.success:
            logger.info("MAAS deploy (reimage): %s (image=%s)", node_id, image or "default")
        return result

    def get_status(self, node_id: str) -> str:
        """Get the MAAS status of a machine."""
        sys_id = self._get_system_id(node_id)
        result = self._request(f"machines/{sys_id}/")
        if result.success and result.data:
            return result.data.get("status_name", "UNKNOWN")
        return "UNKNOWN"

    def set_metadata(self, node_id: str, key: str, value: str) -> BackendResult:
        """Set a tag on a MAAS machine."""
        sys_id = self._get_system_id(node_id)
        tag_name = f"nlm-{key}-{value}".replace(" ", "-").lower()

        # Create tag if it doesn't exist
        self._request("tags/", method="POST", data={"name": tag_name, "comment": f"NLM: {key}={value}"})

        # Apply tag to machine
        return self._request(
            f"tags/{tag_name}/?op=update_nodes",
            method="POST",
            data={"add": [sys_id]},
        )

    def exec_command(self, node_id: str, command: str) -> BackendResult:
        """Execute a command on a node via SSH (MAAS doesn't have native exec)."""
        import subprocess

        try:
            result = subprocess.run(
                ["ssh", "-o", "StrictHostKeyChecking=no", node_id, command],
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            return BackendResult(
                success=result.returncode == 0,
                message=result.stdout.strip(),
                data={"stdout": result.stdout, "stderr": result.stderr},
                error=result.stderr.strip() if result.returncode != 0 else "",
            )
        except Exception as exc:
            return BackendResult(success=False, error=str(exc))

    # ── MAAS-specific operations ─────────────────────────────────────

    def commission(self, node_id: str) -> BackendResult:
        """Commission a new machine in MAAS."""
        sys_id = self._get_system_id(node_id)
        return self._request(f"machines/{sys_id}/?op=commission", method="POST")

    def get_power_state(self, node_id: str) -> str:
        """Get the power state of a MAAS machine."""
        sys_id = self._get_system_id(node_id)
        result = self._request(f"machines/{sys_id}/?op=query_power_state")
        if result.success and result.data:
            return result.data.get("state", "UNKNOWN")
        return "UNKNOWN"

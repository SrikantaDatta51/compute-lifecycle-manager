"""NLM Adapter Base + BCM Mock + K8s + Bare Metal Mock."""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
import logging

logger = logging.getLogger("nlm.adapters")


@dataclass
class AdapterResult:
    success: bool
    message: str = ""
    data: dict = None

    def __post_init__(self):
        if self.data is None:
            self.data = {}


class NodeBackend(ABC):
    @abstractmethod
    def list_nodes(self) -> list[dict]: ...
    @abstractmethod
    def get_status(self, node_id: str) -> dict: ...
    @abstractmethod
    def cordon(self, node_id: str, reason: str = "") -> AdapterResult: ...
    @abstractmethod
    def uncordon(self, node_id: str) -> AdapterResult: ...
    @abstractmethod
    def drain(self, node_id: str) -> AdapterResult: ...
    @abstractmethod
    def reboot(self, node_id: str) -> AdapterResult: ...


class BCMAdapter(NodeBackend):
    """BCM adapter — mock mode simulates cmsh responses."""

    def __init__(self, mode: str = "mock", head_node: str = "bcm-head.local"):
        self.mode = mode
        self.head_node = head_node
        self._mock_nodes = {}
        logger.info("BCM adapter initialized (mode=%s)", mode)

    def register_mock_node(self, node_id: str, status: str = "up",
                           category: str = "default"):
        self._mock_nodes[node_id] = {
            "id": node_id, "status": status, "category": category,
            "overlay": "default", "uptime": "5d 3h",
        }

    def list_nodes(self) -> list[dict]:
        if self.mode == "mock":
            return list(self._mock_nodes.values())
        # Real mode would SSH to head_node and run cmsh -c 'device list'
        return []

    def get_status(self, node_id: str) -> dict:
        if self.mode == "mock":
            return self._mock_nodes.get(node_id, {"id": node_id, "status": "unknown"})
        return {}

    def cordon(self, node_id: str, reason: str = "") -> AdapterResult:
        if self.mode == "mock":
            if node_id in self._mock_nodes:
                self._mock_nodes[node_id]["status"] = "drained"
                return AdapterResult(True, f"cmsh: device {node_id} drained")
            return AdapterResult(False, f"Device {node_id} not found")
        return AdapterResult(False, "Real BCM not implemented")

    def uncordon(self, node_id: str) -> AdapterResult:
        if self.mode == "mock":
            if node_id in self._mock_nodes:
                self._mock_nodes[node_id]["status"] = "up"
                return AdapterResult(True, f"cmsh: device {node_id} set to up")
            return AdapterResult(False, f"Device {node_id} not found")
        return AdapterResult(False, "Real BCM not implemented")

    def drain(self, node_id: str) -> AdapterResult:
        return self.cordon(node_id, "drain requested")

    def reboot(self, node_id: str) -> AdapterResult:
        if self.mode == "mock":
            logger.info("Mock BCM reboot: %s", node_id)
            return AdapterResult(True, f"cmsh: device {node_id} rebooting")
        return AdapterResult(False, "Real BCM not implemented")


class KubernetesAdapter(NodeBackend):
    """K8s adapter — uses real kubectl if minikube is running."""

    def __init__(self, mode: str = "real", kubeconfig: str = "~/.kube/config"):
        self.mode = mode
        self.kubeconfig = kubeconfig
        logger.info("K8s adapter initialized (mode=%s)", mode)

    def _kubectl(self, args: str) -> tuple[bool, str]:
        import subprocess
        try:
            result = subprocess.run(
                f"kubectl {args}", shell=True, capture_output=True, text=True, timeout=10)
            return result.returncode == 0, result.stdout.strip()
        except Exception as e:
            return False, str(e)

    def list_nodes(self) -> list[dict]:
        ok, out = self._kubectl("get nodes -o json")
        if not ok:
            return []
        import json
        try:
            data = json.loads(out)
            return [{"id": n["metadata"]["name"],
                      "status": n["status"]["conditions"][-1]["type"]}
                    for n in data.get("items", [])]
        except Exception:
            return []

    def get_status(self, node_id: str) -> dict:
        ok, out = self._kubectl(f"get node {node_id} -o json")
        if not ok:
            return {"id": node_id, "status": "not_found"}
        import json
        try:
            data = json.loads(out)
            conditions = {c["type"]: c["status"] for c in data["status"]["conditions"]}
            return {"id": node_id, "conditions": conditions,
                    "schedulable": not data["spec"].get("unschedulable", False)}
        except Exception:
            return {"id": node_id, "status": "parse_error"}

    def cordon(self, node_id: str, reason: str = "") -> AdapterResult:
        ok, out = self._kubectl(f"cordon {node_id}")
        return AdapterResult(ok, out)

    def uncordon(self, node_id: str) -> AdapterResult:
        ok, out = self._kubectl(f"uncordon {node_id}")
        return AdapterResult(ok, out)

    def drain(self, node_id: str) -> AdapterResult:
        ok, out = self._kubectl(
            f"drain {node_id} --ignore-daemonsets --delete-emptydir-data --timeout=120s")
        return AdapterResult(ok, out)

    def reboot(self, node_id: str) -> AdapterResult:
        return AdapterResult(False, "K8s reboot not supported — use BMC")


class BareMetalAdapter(NodeBackend):
    """Bare metal adapter — mock IPMI/Redfish responses for local dev."""

    def __init__(self, mode: str = "mock"):
        self.mode = mode
        self._mock_nodes: dict[str, dict] = {}
        self._injected_faults: dict[str, list[str]] = {}
        logger.info("BareMetalAdapter initialized (mode=%s)", mode)

    def register_mock_node(self, node_id: str):
        self._mock_nodes[node_id] = {
            "id": node_id, "power": "on",
            "sel_events": [], "sensors": {
                "GPU_Temp": "45C", "CPU_Temp": "38C",
                "PSU1_Status": "OK", "PSU2_Status": "OK",
                "Fan1_RPM": "12000", "Fan2_RPM": "11800",
            },
        }

    def inject_fault(self, node_id: str, fault: str):
        if node_id not in self._mock_nodes:
            self.register_mock_node(node_id)
        if node_id not in self._injected_faults:
            self._injected_faults[node_id] = []
        self._injected_faults[node_id].append(fault)

        # Update mock sensors based on fault
        n = self._mock_nodes[node_id]
        if fault == "psu_fail":
            n["sensors"]["PSU1_Status"] = "FAILED"
            n["sel_events"].append("PSU1 failure detected")
        elif fault == "thermal_90c":
            n["sensors"]["GPU_Temp"] = "92C"
            n["sel_events"].append("GPU temperature critical: 92C")
        elif fault == "power_off":
            n["power"] = "off"
            n["sel_events"].append("System power off")
        elif fault == "memory_ecc":
            n["sel_events"].append("Uncorrectable ECC error detected")
        elif fault == "nvme_smart":
            n["sel_events"].append("NVMe SMART: reallocated sectors = 15")

    def list_nodes(self) -> list[dict]:
        return [{"id": k, "power": v["power"]} for k, v in self._mock_nodes.items()]

    def get_status(self, node_id: str) -> dict:
        return self._mock_nodes.get(node_id, {"id": node_id, "status": "unknown"})

    def get_sel_events(self, node_id: str) -> list[str]:
        n = self._mock_nodes.get(node_id)
        return n["sel_events"] if n else []

    def get_sensors(self, node_id: str) -> dict:
        n = self._mock_nodes.get(node_id)
        return n["sensors"] if n else {}

    def get_faults(self, node_id: str) -> list[str]:
        return self._injected_faults.get(node_id, [])

    def cordon(self, node_id: str, reason: str = "") -> AdapterResult:
        logger.info("BareMetalAdapter cordon: %s (IPMI: no-op, NLM tracks state)", node_id)
        return AdapterResult(True, f"Bare metal cordon noted for {node_id}")

    def uncordon(self, node_id: str) -> AdapterResult:
        logger.info("BareMetalAdapter uncordon: %s", node_id)
        return AdapterResult(True, f"Bare metal uncordon noted for {node_id}")

    def drain(self, node_id: str) -> AdapterResult:
        return AdapterResult(True, f"Bare metal drain — no workload manager, cordon only")

    def reboot(self, node_id: str) -> AdapterResult:
        if self.mode == "mock":
            logger.info("Mock IPMI reboot: ipmitool -H %s power cycle", node_id)
            if node_id in self._mock_nodes:
                self._mock_nodes[node_id]["power"] = "on"
            return AdapterResult(True, f"IPMI power cycle: {node_id}")
        return AdapterResult(False, "Real IPMI not implemented")


def get_adapter(backend: str, mode: str = "mock", **kwargs) -> NodeBackend:
    if backend == "bcm":
        return BCMAdapter(mode=mode, **kwargs)
    elif backend == "kubernetes":
        return KubernetesAdapter(mode=mode, **kwargs)
    elif backend == "bare_metal":
        return BareMetalAdapter(mode=mode)
    raise ValueError(f"Unknown backend: {backend}")

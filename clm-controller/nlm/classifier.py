"""NLM Failure Classifier — 15 rules + Incident Correlator."""
from __future__ import annotations
import uuid
import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from .models import (
    ClassificationResult, FailureClass, Severity, Incident, Node,
)

logger = logging.getLogger("nlm.classifier")


# ── Classification Rules ──
RULES: list[dict] = [
    {"id": 1, "event": "xid_79", "class": FailureClass.HW_GPU_FATAL, "confidence": 0.95,
     "severity": Severity.CRITICAL, "action": "auto-cordon → RMA", "route": "dc-infra",
     "desc": "GPU fallen off bus"},
    {"id": 2, "event": "xid_64", "class": FailureClass.HW_GPU_MEMORY, "confidence": 0.95,
     "severity": Severity.CRITICAL, "action": "auto-cordon → RMA", "route": "dc-infra",
     "desc": "ECC page retire failure"},
    {"id": 3, "event": "xid_48", "class": FailureClass.HW_GPU_MEMORY, "confidence": 0.98,
     "severity": Severity.CRITICAL, "action": "auto-cordon → RMA", "route": "dc-infra",
     "desc": "Double-bit ECC error"},
    {"id": 4, "event": "xid_94", "class": FailureClass.HW_GPU_CONTAINED, "confidence": 0.90,
     "severity": Severity.HIGH, "action": "auto-cordon → Repair", "route": "compute",
     "desc": "Contained ECC (driver reset may fix)"},
    {"id": 5, "event": "xid_95", "class": FailureClass.HW_GPU_MEMORY, "confidence": 0.98,
     "severity": Severity.CRITICAL, "action": "emergency drain → RMA", "route": "dc-infra",
     "desc": "Uncontained ECC error"},
    {"id": 6, "event": "ecc_uncorrectable", "class": FailureClass.HW_GPU_MEMORY, "confidence": 0.98,
     "severity": Severity.CRITICAL, "action": "auto-cordon → RMA", "route": "dc-infra",
     "desc": "ECC uncorrectable > 0"},
    {"id": 7, "event": "ecc_correctable_high", "class": FailureClass.HW_MEMORY_PRED, "confidence": 0.85,
     "severity": Severity.MEDIUM, "action": "schedule maintenance", "route": "compute",
     "desc": "ECC correctable > 1000/7d — predictive"},
    {"id": 8, "event": "nvlink_uncorrectable", "class": FailureClass.HW_NVSWITCH, "confidence": 0.90,
     "severity": Severity.CRITICAL, "action": "auto-cordon → RMA", "route": "dc-infra",
     "desc": "NVLink uncorrectable errors"},
    {"id": 9, "event": "ib_crc_high", "class": FailureClass.NET_TRANSCEIVER, "confidence": 0.90,
     "severity": Severity.HIGH, "action": "cordon → Repair", "route": "network",
     "desc": "IB CRC > 1000/hr — likely transceiver"},
    {"id": 10, "event": "ib_switch_multi", "class": FailureClass.NET_SWITCH, "confidence": 0.88,
     "severity": Severity.HIGH, "action": "incident → Network", "route": "network",
     "desc": "3+ IB errors on same switch"},
    {"id": 11, "event": "smart_reallocated", "class": FailureClass.HW_NVME, "confidence": 0.92,
     "severity": Severity.HIGH, "action": "auto-cordon → RMA", "route": "dc-infra",
     "desc": "SMART reallocated sectors > 10"},
    {"id": 12, "event": "psu_fail", "class": FailureClass.HW_PSU, "confidence": 0.95,
     "severity": Severity.CRITICAL, "action": "auto-cordon → RMA", "route": "dc-infra",
     "desc": "PSU failure detected via IPMI"},
    {"id": 13, "event": "thermal_critical", "class": FailureClass.HW_THERMAL, "confidence": 0.95,
     "severity": Severity.CRITICAL, "action": "emergency drain", "route": "dc-infra",
     "desc": "GPU temp > 90°C"},
    {"id": 14, "event": "rack_multi_fail", "class": FailureClass.INFRA_RACK, "confidence": 0.88,
     "severity": Severity.CRITICAL, "action": "incident → DC Ops", "route": "dc-infra",
     "desc": "3+ nodes in same rack failed"},
    {"id": 15, "event": "cpu_stress_fail", "class": FailureClass.HW_CPU, "confidence": 0.90,
     "severity": Severity.HIGH, "action": "cordon → Repair", "route": "compute",
     "desc": "stress-ng / memtester failure on CPU node"},
]

_RULE_MAP = {r["event"]: r for r in RULES}


def classify(event_type: str, details: str = "") -> ClassificationResult:
    rule = _RULE_MAP.get(event_type)
    if rule is None:
        return ClassificationResult(
            failure_class=FailureClass.UNKNOWN, confidence=0.0,
            severity=Severity.INFO, recommended_action="manual triage",
            route_to="compute", details=f"Unknown event: {event_type}",
        )
    return ClassificationResult(
        failure_class=rule["class"], confidence=rule["confidence"],
        severity=rule["severity"], recommended_action=rule["action"],
        route_to=rule["route"],
        details=details or rule["desc"],
    )


# ── Incident Correlator ──
class IncidentCorrelator:
    def __init__(self):
        self._recent_events: list[dict] = []
        self._window = timedelta(minutes=5)

    def add_event(self, node: Node, event_type: str, timestamp: datetime | None = None):
        ts = timestamp or datetime.now(timezone.utc)
        self._recent_events.append({
            "node_id": node.id,
            "rack": node.location.rack,
            "switch": node.location.switch,
            "pdu": node.location.pdu,
            "event_type": event_type,
            "timestamp": ts,
        })
        cutoff = ts - self._window
        self._recent_events = [e for e in self._recent_events if e["timestamp"] > cutoff]

    def check_correlations(self) -> list[Incident]:
        incidents = []
        now = datetime.now(timezone.utc)
        cutoff = now - self._window

        active = [e for e in self._recent_events if e["timestamp"] > cutoff]

        # Rack correlation
        by_rack = defaultdict(list)
        for e in active:
            if e["rack"]:
                by_rack[e["rack"]].append(e)
        for rack, events in by_rack.items():
            nodes_set = {e["node_id"] for e in events}
            if len(nodes_set) >= 3:
                incidents.append(Incident(
                    id=f"INC-RACK-{rack}-{uuid.uuid4().hex[:6]}",
                    incident_type="rack",
                    affected_nodes=list(nodes_set),
                    classification=FailureClass.INFRA_RACK,
                    severity=Severity.CRITICAL,
                    route_to="dc-infra",
                    details=f"Rack {rack}: {len(nodes_set)} nodes affected",
                ))

        # Switch correlation
        by_switch = defaultdict(list)
        for e in active:
            if e["switch"] and "ib" in e["event_type"]:
                by_switch[e["switch"]].append(e)
        for sw, events in by_switch.items():
            nodes_set = {e["node_id"] for e in events}
            if len(nodes_set) >= 3:
                incidents.append(Incident(
                    id=f"INC-SW-{sw}-{uuid.uuid4().hex[:6]}",
                    incident_type="switch",
                    affected_nodes=list(nodes_set),
                    classification=FailureClass.NET_SWITCH,
                    severity=Severity.HIGH,
                    route_to="network",
                    details=f"Switch {sw}: {len(nodes_set)} nodes with IB errors",
                ))

        # PDU correlation
        by_pdu = defaultdict(list)
        for e in active:
            if e["pdu"] and "psu" in e["event_type"]:
                by_pdu[e["pdu"]].append(e)
        for pdu, events in by_pdu.items():
            nodes_set = {e["node_id"] for e in events}
            if len(nodes_set) >= 2:
                incidents.append(Incident(
                    id=f"INC-PDU-{pdu}-{uuid.uuid4().hex[:6]}",
                    incident_type="pdu",
                    affected_nodes=list(nodes_set),
                    classification=FailureClass.INFRA_PDU,
                    severity=Severity.CRITICAL,
                    route_to="dc-infra",
                    details=f"PDU {pdu}: {len(nodes_set)} nodes lost power",
                ))

        return incidents

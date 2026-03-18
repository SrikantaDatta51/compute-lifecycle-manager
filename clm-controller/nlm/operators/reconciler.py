"""NLM Reconciler Operator — observe, classify, write operation-requests.

Sits above existing tools (K8s NPD, BCM metrics, DCGM).
Does NOT replace them. Observes their output, classifies faults,
and writes operation-request YAMLs for Ansible Tower to execute.

K8s:   NPD cordons → NLM observes + upgrades priority + records
BCM:   metrics fire → NLM classifies → writes day2_cordon op-request
BMaaS: metrics fire → NLM classifies → writes maintenance_request (awaits customer)
"""
from __future__ import annotations

import logging
from typing import Any

from nlm import db, gitops
from nlm.classifier import classify, IncidentCorrelator
from nlm.cordon import cordon as do_cordon
from nlm.statemachine import StateMachine, TransitionDeniedError
from nlm.alerts import send_alert
from nlm.models import Node, NodeState, CordonPriority, Severity
from .base import Operator

logger = logging.getLogger("nlm.operators.reconciler")

HEALTH_CRITICAL = 0.5
HEALTH_WARNING = 0.7

_HEALTH_FAULT_MAP = [
    (0.2, "xid_79"),
    (0.3, "xid_94"),
    (0.4, "ib_crc_high"),
    (0.5, "ecc_correctable_high"),
]


def _infer_fault(node: Node) -> str:
    for threshold, fault in _HEALTH_FAULT_MAP:
        if node.health_score <= threshold:
            return fault
    return "ecc_correctable_high"


class Reconciler(Operator):
    """Core reconciliation loop — observe, classify, write operation-requests."""

    def __init__(self, interval: int = 60) -> None:
        super().__init__(interval)
        self._sm = StateMachine()
        self._correlator = IncidentCorrelator()

    @property
    def name(self) -> str:
        return "reconciler"

    async def run_once(self) -> dict[str, Any]:
        policy = gitops.read_policy("health-thresholds")
        crit = (policy or {}).get("spec", {}).get("critical_threshold", HEALTH_CRITICAL)
        warn = (policy or {}).get("spec", {}).get("warning_threshold", HEALTH_WARNING)

        nodes = db.list_nodes()
        actions = {
            "nodes_checked": len(nodes),
            "health_alerts": 0,
            "auto_cordons": 0,
            "op_requests_written": 0,
            "incidents_created": 0,
            "state_corrections": 0,
        }

        for node in nodes:
            if node.state in (NodeState.DECOMMISSIONED, NodeState.RMA):
                continue

            # Already handled by another mechanism? Still write GitOps trail
            if node.health_score < crit:
                self._handle_critical(node, actions)

            elif node.health_score < warn and not node.cordon.is_cordoned:
                actions["health_alerts"] += 1

        # Incident correlation
        incidents = self._correlator.check_correlations()
        for inc in incidents:
            db.save_incident(inc)
            gitops.write_incident(
                inc.id, inc.incident_type,
                inc.affected_nodes, inc.severity.value,
                inc.details, inc.route_to,
            )
            actions["incidents_created"] += 1

        # Desired-state reconciliation
        for ds in gitops.list_desired_states():
            node_id = ds.get("metadata", {}).get("name", "")
            wanted = ds.get("spec", {}).get("desired_state", "")
            if not node_id or not wanted:
                continue
            node = db.get_node(node_id)
            if not node or node.state.value == wanted:
                continue
            for t in self._sm.get_valid_transitions(node.state):
                if t["to"] == wanted:
                    try:
                        self._sm.transition(node, t["trigger"],
                                            operator="gitops-reconciler")
                        db.save_node(node)
                        actions["state_corrections"] += 1
                    except TransitionDeniedError:
                        pass
                    break

        return actions

    def _handle_critical(self, node: Node, actions: dict) -> None:
        """Handle a critically unhealthy node."""
        fault_type = _infer_fault(node)
        result = classify(fault_type)
        is_bmaas = "bmaas" in (node.location.environment or "").lower()
        is_p0 = result.severity in (Severity.CRITICAL,)

        # ── K8s + BCM Managed: act immediately ──
        # ── BMaaS P0: act immediately (safety override) ──
        if not is_bmaas or is_p0:
            # 1. In-memory cordon
            try:
                do_cordon(node, owner="nlm-reconciler",
                          priority=CordonPriority.P0,
                          reason=f"Auto: {result.failure_class.value}")
                actions["auto_cordons"] += 1
            except Exception as exc:
                logger.warning("Cordon failed %s: %s", node.id, exc)

            # 2. Operation-request: day2_cordon
            gitops.write_operation_request(
                operation="day2_cordon",
                targets=[node.id],
                parameters={
                    "reason_type": "fault",
                    "ticket_id": f"NLM-{node.id[:8]}",
                },
                requested_by="nlm-reconciler@nlm.cic.io",
                auto_approve=True,
                reason=f"Auto: {result.failure_class.value} "
                       f"(health={node.health_score:.2f})",
                nlm_metadata={
                    "classification": result.failure_class.value,
                    "confidence": result.confidence,
                    "severity": result.severity.value,
                    "priority": "P0",
                },
            )
            actions["op_requests_written"] += 1

            # 3. State transition
            if node.state in (NodeState.CERTIFIED_READY, NodeState.TESTING,
                              NodeState.BURN_IN):
                try:
                    valid = self._sm.get_valid_triggers(node.state)
                    repair_triggers = [t for t in valid if "fail" in t or "timeout" in t]
                    if repair_triggers:
                        self._sm.transition(node, repair_triggers[0],
                                            operator="nlm-reconciler")
                        actions["state_corrections"] += 1
                except TransitionDeniedError:
                    pass

            # 4. Operation-request: debug_bundle (on repair entry)
            if node.state == NodeState.REPAIR:
                gitops.write_operation_request(
                    operation="debug_bundle",
                    targets=[node.id],
                    parameters={"upload_to_s3": True},
                    requested_by="nlm-reconciler@nlm.cic.io",
                    auto_approve=True,
                    reason=f"Auto log collection: {result.failure_class.value}",
                )
                actions["op_requests_written"] += 1

            # 5. GitOps records
            gitops.write_cordon(node.id, "nlm-reconciler", "P0",
                                f"{result.failure_class.value}: {result.details}")
            gitops.write_desired_state(node.id, node.state.value,
                                       operator="nlm-reconciler")

        # ── BMaaS non-P0: customer approval required ──
        else:
            gitops.write_maintenance_request(
                node_id=node.id,
                tenant=node.tenant or "unknown",
                issue=f"{result.failure_class.value}: {result.details}",
                severity=result.severity.value,
                operator="nlm-reconciler",
            )
            actions["op_requests_written"] += 1

            # Alert to customer-facing team (not dc-infra)
            send_alert(
                node, result.severity, "bmaas-customer",
                f"[BMaaS] Maintenance needed: {node.id} — "
                f"{result.failure_class.value} ({result.details}). "
                f"Customer approval required.",
            )

        # Common: alert + correlator + save
        if not is_bmaas or is_p0:
            send_alert(
                node, result.severity, result.route_to,
                f"[Reconciler] {result.failure_class.value}: "
                f"{result.details} (health={node.health_score:.2f})",
            )

        actions["health_alerts"] += 1
        self._correlator.add_event(node, fault_type)
        db.save_node(node)

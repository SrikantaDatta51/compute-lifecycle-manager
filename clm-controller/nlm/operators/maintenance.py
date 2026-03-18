"""NLM Maintenance Orchestrator — timeouts, rack-aware batching, BMaaS approval gate.

Enforces state timeouts from node-states.yml,
orchestrates rolling maintenance (max 2/rack),
processes BMaaS maintenance approvals,
and triggers appropriate Ansible playbooks via operation-requests.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any

from nlm import db, gitops
from nlm.statemachine import StateMachine, TransitionDeniedError
from nlm.alerts import send_alert
from nlm.models import Node, NodeState, Severity
from .base import Operator

logger = logging.getLogger("nlm.operators.maintenance")

STATE_TIMEOUTS: dict[NodeState, tuple[float, str]] = {
    NodeState.PROVISIONING:    (4.0,   "provision_timeout"),
    NodeState.BURN_IN:         (72.0,  "burn_in_fail"),
    NodeState.TESTING:         (8.0,   "l1_fail"),
    NodeState.DRAINING:        (2.0,   "drain_timeout"),
    NodeState.EMERGENCY_DRAIN: (0.5,   "drain_complete"),
}

MAX_CONCURRENT_PER_RACK = 2


class MaintenanceOrchestrator(Operator):
    """Timeout enforcement + rack-aware rolling maintenance + BMaaS approval gate."""

    def __init__(self, interval: int = 120) -> None:
        super().__init__(interval)
        self._sm = StateMachine()

    @property
    def name(self) -> str:
        return "maintenance"

    async def run_once(self) -> dict[str, Any]:
        nodes = db.list_nodes()
        now = datetime.now(timezone.utc)
        actions = {
            "nodes_checked": len(nodes),
            "timeouts_enforced": 0,
            "maintenance_started": 0,
            "rack_limited": 0,
            "approvals_processed": 0,
            "op_requests_written": 0,
        }

        # ── 1. Timeout enforcement ──
        for node in nodes:
            if node.state not in STATE_TIMEOUTS or not node.state_since:
                continue
            timeout_hours, trigger = STATE_TIMEOUTS[node.state]
            deadline = node.state_since + timedelta(hours=timeout_hours)
            if now > deadline:
                elapsed = (now - node.state_since).total_seconds() / 3600
                try:
                    event = self._sm.transition(node, trigger,
                                                operator="nlm-maintenance")
                    db.save_node(node)
                    db.save_event(event)
                    actions["timeouts_enforced"] += 1

                    gitops.write_desired_state(node.id, node.state.value,
                                               operator="nlm-maintenance")

                    # Generate appropriate op-request for the transition
                    if node.state == NodeState.EMERGENCY_DRAIN:
                        gitops.write_operation_request(
                            operation="day2_cordon",
                            targets=[node.id],
                            parameters={"reason_type": "fault"},
                            requested_by="nlm-maintenance@nlm.cic.io",
                            auto_approve=True,
                            reason=f"Timeout: stuck in {event.from_state.value} "
                                   f"for {elapsed:.1f}h",
                        )
                        actions["op_requests_written"] += 1

                    send_alert(
                        node, Severity.HIGH, "compute",
                        f"[Maintenance] Timeout: {node.id} in "
                        f"{event.from_state.value} for {elapsed:.1f}h → "
                        f"{event.to_state.value}",
                    )
                except TransitionDeniedError as exc:
                    logger.warning("Timeout denied: %s — %s", node.id, exc)

        # ── 2. Rack-aware rolling maintenance ──
        maint_nodes = [n for n in nodes
                       if n.state == NodeState.SCHEDULED_MAINTENANCE]
        if maint_nodes:
            repair_nodes = [n for n in nodes if n.state == NodeState.REPAIR]
            active_per_rack: dict[str, int] = defaultdict(int)
            for n in repair_nodes:
                active_per_rack[n.location.rack] += 1

            by_rack: dict[str, list[Node]] = defaultdict(list)
            for n in maint_nodes:
                by_rack[n.location.rack].append(n)

            for rack, rack_nodes in by_rack.items():
                slots = MAX_CONCURRENT_PER_RACK - active_per_rack.get(rack, 0)
                if slots <= 0:
                    actions["rack_limited"] += len(rack_nodes)
                    continue
                for node in rack_nodes[:slots]:
                    try:
                        event = self._sm.transition(node, "repair_start",
                                                    operator="nlm-maintenance")
                        db.save_node(node)
                        db.save_event(event)
                        actions["maintenance_started"] += 1

                        # Op-request: collect debug logs before repair
                        gitops.write_operation_request(
                            operation="debug_bundle",
                            targets=[node.id],
                            parameters={"upload_to_s3": True},
                            requested_by="nlm-maintenance@nlm.cic.io",
                            auto_approve=True,
                            reason="Pre-repair log collection",
                        )
                        gitops.write_desired_state(node.id, node.state.value,
                                                   operator="nlm-maintenance")
                        actions["op_requests_written"] += 1

                    except TransitionDeniedError as exc:
                        logger.warning("Maint start denied: %s — %s",
                                       node.id, exc)

        # ── 3. BMaaS approval gate processing ──
        maint_requests = gitops.list_maintenance_requests()
        for req in maint_requests:
            status = req.get("status", "")
            approved_by = req.get("approved_by", "")
            if status == "awaiting_customer_approval":
                continue  # Still waiting
            if not approved_by:
                continue  # Not yet approved

            # Customer approved — proceed with maintenance
            targets = req.get("targets", [])
            for nid in targets:
                node = db.get_node(nid)
                if not node:
                    continue
                if node.state == NodeState.CUSTOMER_ASSIGNED:
                    try:
                        # Start drain process
                        event = self._sm.transition(
                            node, "drain_requested",
                            operator="nlm-maintenance-bmaas",
                        )
                        db.save_node(node)
                        db.save_event(event)
                        actions["approvals_processed"] += 1

                        gitops.write_operation_request(
                            operation="day2_cordon",
                            targets=[nid],
                            parameters={
                                "reason_type": "maintenance",
                                "ticket_id": req.get("_filename", ""),
                            },
                            requested_by="nlm-maintenance@nlm.cic.io",
                            approved_by=approved_by,
                            reason=f"Customer-approved maintenance: "
                                   f"{req.get('reason', '')}",
                        )
                        actions["op_requests_written"] += 1

                    except TransitionDeniedError as exc:
                        logger.warning("BMaaS drain denied: %s — %s",
                                       nid, exc)

        return actions

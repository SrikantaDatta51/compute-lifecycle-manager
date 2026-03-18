"""NLM Testing Scheduler — reads fleet-validator results, manages cert freshness.

NLM does NOT execute tests. The existing tools do:
  - fleet-validator (systemd timer on BCM head node)
  - burnin_suite.yml Ansible playbook
  - DCGMI diagnostics

NLM's role:
  1. Detect stale certs (>24hr) → write burnin_suite op-request
  2. Read test results → pass: certified_ready, fail: repair
  3. Track certification freshness for dashboard
"""
from __future__ import annotations

import logging
import random
from datetime import datetime, timezone, timedelta
from typing import Any

from nlm import db, gitops
from nlm.statemachine import StateMachine, TransitionDeniedError
from nlm.classifier import classify
from nlm.alerts import send_alert
from nlm.models import Node, NodeState, Severity
from .base import Operator

logger = logging.getLogger("nlm.operators.testing")

DEFAULT_L1_INTERVAL_HOURS = 24


class TestingScheduler(Operator):
    """Manages certification freshness via fleet-validator + burnin_suite."""

    def __init__(self, interval: int = 300, mock_mode: bool = True) -> None:
        super().__init__(interval)
        self._sm = StateMachine()
        self._mock_mode = mock_mode
        self._testing_since: dict[str, datetime] = {}

    @property
    def name(self) -> str:
        return "testing"

    async def run_once(self) -> dict[str, Any]:
        policy = gitops.read_policy("test-schedule")
        l1_hours = (policy or {}).get("spec", {}).get(
            "l1_interval_hours", DEFAULT_L1_INTERVAL_HOURS)

        nodes = db.list_nodes()
        now = datetime.now(timezone.utc)
        actions = {
            "nodes_checked": len(nodes),
            "stale_detected": 0,
            "tests_scheduled": 0,
            "tests_passed": 0,
            "tests_failed": 0,
            "op_requests_written": 0,
        }

        # ── 1. Detect stale certifications ──
        for node in nodes:
            if node.state != NodeState.CERTIFIED_READY:
                continue
            if node.customer_protected:
                continue

            stale = False
            if not node.last_certified:
                stale = True
            elif (now - node.last_certified) > timedelta(hours=l1_hours):
                stale = True

            if stale:
                actions["stale_detected"] += 1
                self._schedule_test(node, actions)

        # ── 2. Process nodes currently in testing ──
        testing_nodes = [n for n in nodes if n.state == NodeState.TESTING]
        for node in testing_nodes:
            result = self._get_test_result(node)
            if result is None:
                continue
            if result["passed"]:
                self._handle_pass(node, actions)
            else:
                self._handle_fail(node, result, actions)

        return actions

    def _schedule_test(self, node: Node, actions: dict) -> None:
        """Transition to testing + write burnin_suite op-request."""
        try:
            event = self._sm.transition(node, "testing_scheduled",
                                        operator="nlm-testing")
            db.save_node(node)
            db.save_event(event)
            self._testing_since[node.id] = datetime.now(timezone.utc)
            actions["tests_scheduled"] += 1

            # Op-request: trigger burn-in via Ansible Tower
            gitops.write_operation_request(
                operation="burnin_suite",
                targets=[node.id],
                parameters={
                    "dcgmi_level": "medium",
                    "nccl_test": "all_reduce",
                    "tests": ["dcgmi_r3", "nccl_all_reduce", "nvbandwidth"],
                    "skip_on_failure": False,
                },
                requested_by="nlm-testing@nlm.cic.io",
                auto_approve=True,
                reason=f"Daily L1 certification (cert stale >24hr)",
                nlm_metadata={"state_transition": "certified_ready → testing"},
            )
            actions["op_requests_written"] += 1

            gitops.write_desired_state(node.id, "testing",
                                       operator="nlm-testing")

        except TransitionDeniedError as exc:
            logger.warning("Cannot schedule test %s: %s", node.id, exc)

    def _get_test_result(self, node: Node) -> dict | None:
        """Read test result from fleet-validator.

        Production: reads fleet-certify.sh output or certification-report.sh JSON
        Mock mode: simulates pass/fail based on health score
        """
        if self._mock_mode:
            started = self._testing_since.get(node.id)
            if not started:
                self._testing_since[node.id] = datetime.now(timezone.utc)
                return None
            if (datetime.now(timezone.utc) - started).total_seconds() < 20:
                return None  # Still "running"

            passed = node.health_score >= 0.7
            if passed and random.random() < 0.05:
                passed = False

            return {
                "passed": passed,
                "level": "L1",
                "tests_run": ["dcgmi_r3", "nccl_all_reduce", "nvbandwidth"],
                "failures": [] if passed else [
                    {"test": "dcgmi_r3", "error": "GPU ECC errors detected"}
                ],
            }

        # Production: read from fleet-validator output
        # TODO: read fleet-certify.sh output via adapter
        return None

    def _handle_pass(self, node: Node, actions: dict) -> None:
        try:
            event = self._sm.transition(node, "l1_pass",
                                        operator="nlm-testing")
            db.save_node(node)
            db.save_event(event)
            actions["tests_passed"] += 1
            self._testing_since.pop(node.id, None)

            gitops.write_desired_state(node.id, "certified_ready",
                                       operator="nlm-testing")

            # Op-request: uncordon after passing
            gitops.write_operation_request(
                operation="day2_uncordon",
                targets=[node.id],
                parameters={"reason_type": "test_passed"},
                requested_by="nlm-testing@nlm.cic.io",
                auto_approve=True,
                reason=f"L1 test passed — recertified",
            )
            actions["op_requests_written"] += 1

        except TransitionDeniedError as exc:
            logger.warning("Pass transition denied: %s — %s", node.id, exc)

    def _handle_fail(self, node: Node, result: dict, actions: dict) -> None:
        try:
            event = self._sm.transition(node, "l1_fail",
                                        operator="nlm-testing")
            db.save_node(node)
            db.save_event(event)
            actions["tests_failed"] += 1
            self._testing_since.pop(node.id, None)

            failures = result.get("failures", [])
            fault_desc = failures[0]["error"] if failures else "Test failure"

            # Op-requests: cordon + debug bundle
            gitops.write_operation_request(
                operation="day2_cordon",
                targets=[node.id],
                parameters={"reason_type": "fault"},
                requested_by="nlm-testing@nlm.cic.io",
                auto_approve=True,
                reason=f"L1 test failed: {fault_desc}",
            )
            gitops.write_operation_request(
                operation="debug_bundle",
                targets=[node.id],
                parameters={"upload_to_s3": True},
                requested_by="nlm-testing@nlm.cic.io",
                auto_approve=True,
                reason=f"Post-failure log collection: {fault_desc}",
            )
            actions["op_requests_written"] += 2

            gitops.write_desired_state(node.id, "repair",
                                       operator="nlm-testing")
            gitops.write_cordon(node.id, "nlm-testing", "P0",
                                f"L1 test failure: {fault_desc}")

            send_alert(
                node, Severity.HIGH, "compute",
                f"[Testing] L1 FAILED: {node.id} — {fault_desc}",
            )

        except TransitionDeniedError as exc:
            logger.warning("Fail transition denied: %s — %s", node.id, exc)

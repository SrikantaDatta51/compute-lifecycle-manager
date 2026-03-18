"""NLM State Machine — 11-state lifecycle engine with YAML config."""
from __future__ import annotations
import uuid
import yaml
import os
import logging
from datetime import datetime, timezone
from typing import Optional
from .models import Node, NodeState, CordonPriority, StateTransitionEvent

logger = logging.getLogger("nlm.statemachine")

CONFIG_PATH = os.environ.get(
    "NLM_STATES_CONFIG",
    os.path.join(os.path.dirname(__file__), "..", "config", "node-states.yml"),
)


class TransitionDeniedError(Exception):
    pass


class StateMachine:
    def __init__(self, config_path: str | None = None):
        path = config_path or CONFIG_PATH
        with open(path) as f:
            self._config = yaml.safe_load(f)
        self._states = self._config["states"]
        self._transitions: list[dict] = self._config["transitions"]
        self._map: dict[tuple[str, str], dict] = {}
        for t in self._transitions:
            self._map[(t["from"], t["trigger"])] = t
        logger.info("StateMachine loaded: %d states, %d transitions",
                     len(self._states), len(self._transitions))

    @property
    def states(self) -> dict:
        return self._states

    def get_valid_triggers(self, state: NodeState) -> list[str]:
        return [t["trigger"] for t in self._transitions if t["from"] == state.value]

    def get_valid_transitions(self, state: NodeState) -> list[dict]:
        return [t for t in self._transitions if t["from"] == state.value]

    def transition(self, node: Node, trigger: str,
                   operator: str = "nlm-controller",
                   metadata: dict | None = None) -> StateTransitionEvent:
        key = (node.state.value, trigger)
        t_def = self._map.get(key)
        if t_def is None:
            valid = self.get_valid_triggers(node.state)
            raise TransitionDeniedError(
                f"Invalid: {node.state.value} --[{trigger}]--> ???. "
                f"Valid triggers: {valid}"
            )

        # Customer protection check
        if node.customer_protected and node.state == NodeState.CUSTOMER_ASSIGNED:
            priority = CordonPriority(t_def.get("priority", "P4"))
            if priority != CordonPriority.P0:
                raise TransitionDeniedError(
                    f"DENIED: Node {node.id} is customer-protected. "
                    f"Only P0 transitions allowed (got {priority.value})."
                )

        target = NodeState(t_def["to"])
        from_state = node.state
        priority = CordonPriority(t_def.get("priority", "P4"))

        event = StateTransitionEvent(
            id=str(uuid.uuid4()),
            node_id=node.id,
            from_state=from_state,
            to_state=target,
            trigger=trigger,
            owner=t_def.get("owner", operator),
            priority=priority,
            metadata=metadata or {},
        )

        try:
            node.state = target
            node.state_since = datetime.now(timezone.utc)
            node.state_reason = trigger
            node.state_owner = event.owner
            node.updated_at = datetime.now(timezone.utc)

            # Auto-cordon on repair/rma states
            if target in (NodeState.REPAIR, NodeState.RMA, NodeState.EMERGENCY_DRAIN):
                node.cordon.is_cordoned = True
                node.cordon.owner = event.owner
                node.cordon.priority = priority
                node.cordon.reason = trigger
                node.cordon.since = datetime.now(timezone.utc)

            # Auto-uncordon on certified_ready
            if target == NodeState.CERTIFIED_READY:
                node.cordon.is_cordoned = False
                node.cordon.owner = ""
                node.cordon.reason = ""
                node.health_score = 1.0
                node.cert_status = "passed"
                node.last_certified = datetime.now(timezone.utc)

            # Customer protection
            if target == NodeState.CUSTOMER_ASSIGNED:
                node.customer_protected = True
            elif from_state == NodeState.CUSTOMER_ASSIGNED:
                node.customer_protected = False

            event.success = True
            logger.info("Transition: %s [%s] --[%s]--> [%s] (owner=%s, P=%s)",
                        node.id, from_state.value, trigger, target.value,
                        event.owner, priority.value)

        except Exception as exc:
            event.success = False
            event.error = str(exc)
            logger.error("Transition FAILED: %s — %s", node.id, exc)
            raise

        return event

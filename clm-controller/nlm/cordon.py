"""NLM Cordon Ownership — P0–P4 Priority Arbitration."""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from .models import Node, CordonPriority, CordonInfo

logger = logging.getLogger("nlm.cordon")


class CordonDeniedError(Exception):
    pass


# Priority values: lower = higher authority
_PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4}


def cordon(node: Node, owner: str, priority: CordonPriority,
           reason: str = "") -> dict:
    """Cordon a node with priority check."""
    if node.cordon.is_cordoned:
        existing = _PRIORITY_ORDER[node.cordon.priority.value]
        requested = _PRIORITY_ORDER[priority.value]
        if requested > existing:
            raise CordonDeniedError(
                f"DENIED: Node {node.id} already cordoned by '{node.cordon.owner}' "
                f"at {node.cordon.priority.value}. Cannot cordon at {priority.value} "
                f"(lower authority)."
            )
        # Higher or equal priority — override
        logger.info("Cordon override: %s — %s (%s) overrides %s (%s)",
                     node.id, owner, priority.value,
                     node.cordon.owner, node.cordon.priority.value)

    node.cordon = CordonInfo(
        is_cordoned=True,
        owner=owner,
        priority=priority,
        reason=reason,
        since=datetime.now(timezone.utc),
    )
    node.updated_at = datetime.now(timezone.utc)

    logger.info("Cordoned: %s by %s (P=%s) — %s",
                 node.id, owner, priority.value, reason)
    return {
        "node_id": node.id,
        "action": "cordoned",
        "owner": owner,
        "priority": priority.value,
        "reason": reason,
    }


def uncordon(node: Node, requester: str, force: bool = False) -> dict:
    """Uncordon a node — only cordon owner can uncordon (unless force/P0)."""
    if not node.cordon.is_cordoned:
        return {"node_id": node.id, "action": "already_uncordoned"}

    if not force and node.cordon.owner != requester:
        # Check if requester has higher priority
        if node.cordon.priority.value in ("P0", "P1"):
            raise CordonDeniedError(
                f"DENIED: Node {node.id} cordoned by '{node.cordon.owner}' "
                f"at {node.cordon.priority.value}. Only the cordon owner can uncordon. "
                f"P0/P1 cordons are non-overridable."
            )
        # Allow if explicit force flag
        raise CordonDeniedError(
            f"DENIED: Node {node.id} cordoned by '{node.cordon.owner}'. "
            f"Only '{node.cordon.owner}' can uncordon (or use --force)."
        )

    prev_owner = node.cordon.owner
    node.cordon = CordonInfo()
    node.updated_at = datetime.now(timezone.utc)

    logger.info("Uncordoned: %s by %s (was: %s)", node.id, requester, prev_owner)
    return {
        "node_id": node.id,
        "action": "uncordoned",
        "by": requester,
        "previous_owner": prev_owner,
    }


def get_cordon_status(node: Node) -> dict:
    return {
        "node_id": node.id,
        "is_cordoned": node.cordon.is_cordoned,
        "owner": node.cordon.owner,
        "priority": node.cordon.priority.value,
        "reason": node.cordon.reason,
        "since": node.cordon.since.isoformat() if node.cordon.since else None,
    }

"""NLM Alert Dispatcher — mock Slack/PagerDuty to console + file."""
from __future__ import annotations
import json
import uuid
import logging
import os
from datetime import datetime, timezone
from .models import AlertEvent, Severity, Node

logger = logging.getLogger("nlm.alerts")
ALERTS_FILE = os.environ.get("NLM_ALERTS_FILE", "nlm-data/alerts.jsonl")

# Channel routing based on failure classification route_to
CHANNEL_MAP = {
    "dc-infra": "#dc-infra-rma",
    "network": "#network-ops",
    "storage": "#storage-ops",
    "compute": "#compute-platform",
    "customer": "#customer-ops",
    "capacity": "#capacity-planning",
    "security": "#security-compliance",
}


def _write_alert(alert: AlertEvent):
    os.makedirs(os.path.dirname(ALERTS_FILE), exist_ok=True)
    with open(ALERTS_FILE, "a") as f:
        f.write(json.dumps({
            "id": alert.id, "node_id": alert.node_id,
            "severity": alert.severity.value, "channel": alert.channel,
            "message": alert.message,
            "timestamp": alert.timestamp.isoformat(),
        }) + "\n")


def send_alert(node: Node, severity: Severity, route_to: str,
               message: str) -> AlertEvent:
    channel = CHANNEL_MAP.get(route_to, "#compute-platform")
    alert = AlertEvent(
        id=str(uuid.uuid4()),
        node_id=node.id,
        severity=severity,
        channel=channel,
        message=message,
    )

    # Console output (rich formatting)
    sev_icon = {"critical": "🔴", "high": "🟡", "medium": "🔵", "low": "⚪", "info": "ℹ️"}
    icon = sev_icon.get(severity.value, "❓")
    print(f"\n{icon} ALERT [{severity.value.upper()}] → {channel}")
    print(f"  Node: {node.id} ({node.location.environment})")
    print(f"  {message}")

    # File output
    _write_alert(alert)
    logger.info("Alert sent: %s → %s [%s]", node.id, channel, severity.value)
    return alert


def send_pagerduty(node: Node, message: str) -> AlertEvent:
    alert = AlertEvent(
        id=str(uuid.uuid4()),
        node_id=node.id,
        severity=Severity.CRITICAL,
        channel="PagerDuty",
        message=message,
    )
    print(f"\n🚨 PAGERDUTY [{node.id}] {message}")
    _write_alert(alert)
    return alert


def get_recent_alerts(limit: int = 20) -> list[dict]:
    if not os.path.exists(ALERTS_FILE):
        return []
    with open(ALERTS_FILE) as f:
        lines = f.readlines()
    alerts = [json.loads(l) for l in lines[-limit:]]
    alerts.reverse()
    return alerts

"""NLM GitOps — operation-request YAML generator.

Generates YAMLs in the **existing bcm-iac operation-request format**
that Ansible Tower already executes on PR merge.

Write path:
  NLM operator → gitops.write_operation_request() → nlm-data/gitops/operation-requests/*.yml
  In production:  NLM → git commit → PR merge → Ansible Tower → playbook execution

Also manages desired-state and policy YAMLs for NLM-internal state tracking.
"""
from __future__ import annotations

import logging
import os
import uuid
import yaml
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("nlm.gitops")

GITOPS_ROOT = os.environ.get(
    "NLM_GITOPS_ROOT",
    os.path.join(os.path.dirname(__file__), "..", "nlm-data", "gitops"),
)


def _ensure_dirs() -> None:
    for sub in ("operation-requests", "desired-state", "cordons",
                "maintenance", "policies", "incidents"):
        os.makedirs(os.path.join(GITOPS_ROOT, sub), exist_ok=True)


def _write_yaml(subdir: str, filename: str, data: dict) -> str:
    _ensure_dirs()
    path = os.path.join(GITOPS_ROOT, subdir, filename)
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    logger.info("GitOps write: %s/%s", subdir, filename)
    return path


def _read_yaml(subdir: str, filename: str) -> dict | None:
    path = os.path.join(GITOPS_ROOT, subdir, filename)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return yaml.safe_load(f)


def _delete_yaml(subdir: str, filename: str) -> bool:
    path = os.path.join(GITOPS_ROOT, subdir, filename)
    if os.path.exists(path):
        os.remove(path)
        logger.info("GitOps delete: %s/%s", subdir, filename)
        return True
    return False


def _list_yaml(subdir: str) -> list[dict]:
    _ensure_dirs()
    dirpath = os.path.join(GITOPS_ROOT, subdir)
    results = []
    if not os.path.isdir(dirpath):
        return results
    for fname in sorted(os.listdir(dirpath)):
        if fname.endswith((".yml", ".yaml")):
            data = _read_yaml(subdir, fname)
            if data:
                data["_filename"] = fname
                results.append(data)
    return results


# ═══════════════════════════════════════════════════════════════════
# Operation Requests — matches bcm-iac/gitops/operation-requests/
# ═══════════════════════════════════════════════════════════════════

def write_operation_request(
    operation: str,
    targets: list[str],
    parameters: dict | None = None,
    requested_by: str = "nlm-controller@nlm.cic.io",
    approved_by: str = "",
    reason: str = "",
    auto_approve: bool = False,
    nlm_metadata: dict | None = None,
) -> str:
    """Generate an operation-request YAML in bcm-iac format.

    In production, this would be a git commit → PR → Ansible Tower executes.
    Locally, the file is written to nlm-data/gitops/operation-requests/.
    """
    req_id = f"auto-{operation}-{targets[0]}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

    data = {
        "operation": operation,
        "targets": targets,
        "parameters": parameters or {},
        "requested_by": requested_by,
        "approved_by": requested_by if auto_approve else approved_by,
        "reason": reason,
    }

    if nlm_metadata:
        data["nlm_metadata"] = nlm_metadata

    return _write_yaml("operation-requests", f"{req_id}.yml", data)


def list_operation_requests() -> list[dict]:
    return _list_yaml("operation-requests")


# ═══════════════════════════════════════════════════════════════════
# Desired State — NLM-internal state tracking
# ═══════════════════════════════════════════════════════════════════

def write_desired_state(node_id: str, desired_state: str,
                        tenant: str = "", labels: dict | None = None,
                        operator: str = "nlm-controller") -> str:
    data = {
        "apiVersion": "nlm.cic.io/v1",
        "kind": "NodeState",
        "metadata": {
            "name": node_id,
            "labels": labels or {},
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": operator,
        },
        "spec": {
            "desired_state": desired_state,
            "tenant": tenant,
        },
    }
    return _write_yaml("desired-state", f"{node_id}.yml", data)


def read_desired_state(node_id: str) -> dict | None:
    return _read_yaml("desired-state", f"{node_id}.yml")


def list_desired_states() -> list[dict]:
    return _list_yaml("desired-state")


# ═══════════════════════════════════════════════════════════════════
# Cordons
# ═══════════════════════════════════════════════════════════════════

def write_cordon(node_id: str, owner: str, priority: str,
                 reason: str, operator: str = "nlm-controller") -> str:
    data = {
        "apiVersion": "nlm.cic.io/v1",
        "kind": "Cordon",
        "metadata": {
            "name": node_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": operator,
        },
        "spec": {"owner": owner, "priority": priority, "reason": reason},
    }
    return _write_yaml("cordons", f"{node_id}.yml", data)


def delete_cordon(node_id: str) -> bool:
    return _delete_yaml("cordons", f"{node_id}.yml")


def list_cordons() -> list[dict]:
    return _list_yaml("cordons")


# ═══════════════════════════════════════════════════════════════════
# Maintenance Requests (BMaaS approval gate)
# ═══════════════════════════════════════════════════════════════════

def write_maintenance_request(
    node_id: str, tenant: str, issue: str, severity: str,
    recommended_window: str = "",
    operator: str = "nlm-controller",
) -> str:
    """Generate a maintenance request that requires customer approval (BMaaS)."""
    data = {
        "operation": "maintenance_request",
        "targets": [node_id],
        "parameters": {
            "issue": issue,
            "severity": severity,
            "recommended_window": recommended_window,
        },
        "requested_by": f"{operator}@nlm.cic.io",
        "approved_by": "",  # Must be filled by partner/customer
        "reason": issue,
        "tenant": tenant,
        "status": "awaiting_customer_approval",
    }
    req_id = f"maint-request-{node_id}-{datetime.now(timezone.utc).strftime('%Y%m%d')}"
    return _write_yaml("maintenance", f"{req_id}.yml", data)


def list_maintenance_requests() -> list[dict]:
    return _list_yaml("maintenance")


# ═══════════════════════════════════════════════════════════════════
# Incidents
# ═══════════════════════════════════════════════════════════════════

def write_incident(incident_id: str, incident_type: str,
                   affected_nodes: list[str], severity: str,
                   details: str, route_to: str) -> str:
    data = {
        "apiVersion": "nlm.cic.io/v1",
        "kind": "Incident",
        "metadata": {
            "name": incident_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        "spec": {
            "type": incident_type,
            "affected_nodes": affected_nodes,
            "severity": severity,
            "details": details,
            "route_to": route_to,
            "resolved": False,
        },
    }
    return _write_yaml("incidents", f"{incident_id}.yml", data)


def list_incidents() -> list[dict]:
    return _list_yaml("incidents")


# ═══════════════════════════════════════════════════════════════════
# Policies
# ═══════════════════════════════════════════════════════════════════

def write_policy(name: str, policy_data: dict) -> str:
    data = {
        "apiVersion": "nlm.cic.io/v1",
        "kind": "Policy",
        "metadata": {
            "name": name,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        "spec": policy_data,
    }
    return _write_yaml("policies", f"{name}.yml", data)


def read_policy(name: str) -> dict | None:
    return _read_yaml("policies", f"{name}.yml")


def seed_default_policies() -> None:
    if not read_policy("health-thresholds"):
        write_policy("health-thresholds", {
            "critical_threshold": 0.5,
            "warning_threshold": 0.7,
            "auto_cordon_below": 0.5,
        })
    if not read_policy("test-schedule"):
        write_policy("test-schedule", {
            "l1_interval_hours": 24,
            "l1_start_utc": "02:00",
            "skip_customer_assigned": True,
        })
    if not read_policy("firmware-baseline"):
        write_policy("firmware-baseline", {
            "gpu_driver": "550.127.05",
            "cuda": "12.4",
            "bios": "1.7",
            "bmc": "2.19.0",
        })

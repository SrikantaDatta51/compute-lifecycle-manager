"""NLM REST API — 22 endpoints + Compute Hub dashboard + Basic Auth + Prometheus."""
from __future__ import annotations
import os
import secrets
import uuid
from dataclasses import asdict
from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, PlainTextResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from typing import Optional
from . import db
from .models import (
    NodeState, CordonPriority, Severity, get_bom_template,
)
from .statemachine import StateMachine, TransitionDeniedError
from .classifier import classify, IncidentCorrelator, RULES
from .cordon import cordon as do_cordon, uncordon as do_uncordon, CordonDeniedError
from .alerts import send_alert, get_recent_alerts
from . import gitops
from .operators.manager import OperatorManager
from .operators.reconciler import Reconciler
from .operators.maintenance import MaintenanceOrchestrator
from .operators.testing import TestingScheduler

app = FastAPI(title="NLM API", version="4.0.0",
              description="Node Lifecycle Management — GitOps Control Plane")

# CORS
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

# Mount static files
_static = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(_static):
    app.mount("/static", StaticFiles(directory=_static, html=True), name="static")

# Basic Auth
security = HTTPBasic()
NLM_USER = os.environ.get("NLM_USER", "admin")
NLM_PASS = os.environ.get("NLM_PASS", "nlm")


def auth(creds: HTTPBasicCredentials = Depends(security)):
    ok = secrets.compare_digest(creds.username, NLM_USER) and \
         secrets.compare_digest(creds.password, NLM_PASS)
    if not ok:
        raise HTTPException(401, "Invalid credentials",
                            headers={"WWW-Authenticate": "Basic"})
    return creds.username


sm = StateMachine()
correlator = IncidentCorrelator()


# ── Request Models ──
class TransitionRequest(BaseModel):
    trigger: str
    operator: str = "api-user"
    metadata: dict = {}

class CordonRequest(BaseModel):
    owner: str
    priority: str = "P3"
    reason: str = ""

class UncordonRequest(BaseModel):
    requester: str
    force: bool = False

class InjectRequest(BaseModel):
    fault: str
    details: str = ""


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/static/index.html")


@app.get("/metrics", include_in_schema=False)
def prometheus_metrics():
    """Prometheus metrics endpoint for Grafana scraping."""
    nodes = db.list_nodes()
    cap = db.get_fleet_capacity()
    lines = ["# HELP nlm_nodes_total Total nodes in NLM fleet",
             "# TYPE nlm_nodes_total gauge",
             f'nlm_nodes_total {cap["total"]}']
    for state, count in cap.get("by_state", {}).items():
        lines.append(f'nlm_node_state{{state="{state}"}} {count}')
    for sku, count in cap.get("by_sku", {}).items():
        lines.append(f'nlm_node_sku{{sku="{sku}"}} {count}')
    for az, count in cap.get("by_az", {}).items():
        lines.append(f'nlm_node_az{{az="{az}"}} {count}')
    cordoned = sum(1 for n in nodes if n.cordon.is_cordoned)
    lines.append(f"nlm_nodes_cordoned_total {cordoned}")
    avg_health = sum(n.health_score for n in nodes) / len(nodes) if nodes else 0
    lines.append(f"nlm_avg_health_score {avg_health:.4f}")
    gpu_avail = sum(1 for n in nodes if n.node_type.value == "gpu"
                    and n.state.value == "certified_ready")
    lines.append(f"nlm_capacity_gpu_available {gpu_avail}")
    return PlainTextResponse("\n".join(lines) + "\n",
                             media_type="text/plain; version=0.0.4")


# ── 1. Fleet Capacity ──
@app.get("/api/v1/fleet/capacity")
def fleet_capacity(user: str = Depends(auth)):
    return db.get_fleet_capacity()


# ── 2. List Nodes ──
@app.get("/api/v1/nodes")
def list_nodes(state: Optional[str] = None, az: Optional[str] = None,
               node_type: Optional[str] = None, backend: Optional[str] = None,
               user: str = Depends(auth)):
    nodes = db.list_nodes(state=state, az=az, node_type=node_type, backend=backend)
    return [_node_to_dict(n) for n in nodes]


# ── 3. Get Node ──
@app.get("/api/v1/nodes/{node_id}")
def get_node(node_id: str, user: str = Depends(auth)):
    node = db.get_node(node_id)
    if not node:
        raise HTTPException(404, f"Node {node_id} not found")
    return _node_to_dict(node)


# ── 4. Transition ──
@app.put("/api/v1/nodes/{node_id}/state")
def transition_node(node_id: str, req: TransitionRequest, user: str = Depends(auth)):
    node = db.get_node(node_id)
    if not node:
        raise HTTPException(404, f"Node {node_id} not found")
    try:
        event = sm.transition(node, req.trigger, req.operator, req.metadata)
        db.save_node(node)
        db.save_event(event)
        return {"status": "ok", "event_id": event.id,
                "from": event.from_state.value, "to": event.to_state.value}
    except TransitionDeniedError as e:
        raise HTTPException(403, str(e))


# ── 5. Cordon ──
@app.post("/api/v1/nodes/{node_id}/cordon")
def cordon_node(node_id: str, req: CordonRequest, user: str = Depends(auth)):
    node = db.get_node(node_id)
    if not node:
        raise HTTPException(404, f"Node {node_id} not found")
    try:
        result = do_cordon(node, req.owner, CordonPriority(req.priority), req.reason)
        db.save_node(node)
        return result
    except CordonDeniedError as e:
        raise HTTPException(403, str(e))


# ── 6. Uncordon ──
@app.post("/api/v1/nodes/{node_id}/uncordon")
def uncordon_node(node_id: str, req: UncordonRequest, user: str = Depends(auth)):
    node = db.get_node(node_id)
    if not node:
        raise HTTPException(404, f"Node {node_id} not found")
    try:
        result = do_uncordon(node, req.requester, req.force)
        db.save_node(node)
        return result
    except CordonDeniedError as e:
        raise HTTPException(403, str(e))


# ── 7. Inject Fault ──
@app.post("/api/v1/nodes/{node_id}/inject")
def inject_fault(node_id: str, req: InjectRequest, user: str = Depends(auth)):
    node = db.get_node(node_id)
    if not node:
        raise HTTPException(404, f"Node {node_id} not found")
    result = classify(req.fault, req.details)
    correlator.add_event(node, req.fault)
    if result.severity in (Severity.CRITICAL, Severity.HIGH):
        try:
            do_cordon(node, "nlm-controller", CordonPriority.P0, result.recommended_action)
        except CordonDeniedError:
            pass
    send_alert(node, result.severity, result.route_to,
               f"[{req.fault}] {result.details} -> {result.recommended_action}")
    incidents = correlator.check_correlations()
    for inc in incidents:
        db.save_incident(inc)
    node.health_score = max(0.0, node.health_score - 0.3)
    db.save_node(node)
    return {
        "classification": result.failure_class.value,
        "confidence": result.confidence,
        "severity": result.severity.value,
        "action": result.recommended_action,
        "route_to": result.route_to,
        "incidents_created": len(incidents),
    }


# ── 8. Incidents (Rootly-style mock data) ──
@app.get("/api/v1/incidents")
def list_incidents(resolved: Optional[bool] = None, user: str = Depends(auth)):
    """Return Rootly-style incident mock data."""
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    rootly_incidents = [
        {
            "id": "INC-2026-0312", "title": "GPU Xid 79 Multi-Node Correlation — KR1A Rack B01",
            "severity": "critical", "status": "mitigated",
            "service": "GPU Compute — DGX B200", "environment": "KR1A Prod",
            "started_at": (now - timedelta(hours=4)).isoformat(),
            "mitigated_at": (now - timedelta(hours=2)).isoformat(),
            "resolved_at": None,
            "commander": "SRE-Kim", "slack_channel": "#inc-gpu-kr1a-0312",
            "rootly_url": "https://rootly.com/incidents/INC-2026-0312",
            "summary": "Multiple Xid 79 (GPU fallen off bus) events on gpu-b200-009 and gpu-b200-010. Auto-cordoned by NLM controller. RMA initiated for affected GPUs.",
            "affected_nodes": ["gpu-b200-009", "gpu-b200-010"],
            "timeline": [
                {"time": (now - timedelta(hours=4)).isoformat(), "event": "Alert fired: nlm_avg_health_score < 0.5"},
                {"time": (now - timedelta(hours=3, minutes=55)).isoformat(), "event": "Incident created automatically by Rootly via PagerDuty"},
                {"time": (now - timedelta(hours=3, minutes=50)).isoformat(), "event": "Commander SRE-Kim assigned"},
                {"time": (now - timedelta(hours=3, minutes=30)).isoformat(), "event": "Root cause identified: NVSwitch firmware mismatch after rolling update"},
                {"time": (now - timedelta(hours=2)).isoformat(), "event": "Nodes cordoned, workloads drained. Mitigation complete."},
            ],
            "labels": ["gpu", "xid-79", "hardware", "auto-cordon"],
            "action_items": [
                {"task": "RMA gpu-b200-009 GPU slot 6", "owner": "HW-Ops", "status": "in_progress"},
                {"task": "Validate NVSwitch FW version alignment", "owner": "FW-Team", "status": "done"},
            ]
        },
        {
            "id": "INC-2026-0310", "title": "InfiniBand Link Flapping — KR1B BMaaS Spine",
            "severity": "high", "status": "resolved",
            "service": "Network Fabric — InfiniBand", "environment": "KR1B Prod BMaaS",
            "started_at": (now - timedelta(days=2, hours=6)).isoformat(),
            "mitigated_at": (now - timedelta(days=2, hours=3)).isoformat(),
            "resolved_at": (now - timedelta(days=1, hours=18)).isoformat(),
            "commander": "NetOps-Park", "slack_channel": "#inc-network-kr1b-0310",
            "rootly_url": "https://rootly.com/incidents/INC-2026-0310",
            "summary": "Intermittent IB link flapping on spine switch affecting 4 nodes in rack-BM01. Traced to faulty QSFP transceiver. Replaced and validated.",
            "affected_nodes": ["gpu-bm-001", "gpu-bm-002", "gpu-bm-003", "gpu-bm-004"],
            "timeline": [
                {"time": (now - timedelta(days=2, hours=6)).isoformat(), "event": "Alert: ib_port_flap_rate > 5/min on spine-kr1b-01"},
                {"time": (now - timedelta(days=2, hours=5, minutes=45)).isoformat(), "event": "PagerDuty escalation to NetOps"},
                {"time": (now - timedelta(days=2, hours=5)).isoformat(), "event": "Identified faulty QSFP in port 24 of spine-kr1b-01"},
                {"time": (now - timedelta(days=2, hours=3)).isoformat(), "event": "Transceiver replaced, links stable"},
                {"time": (now - timedelta(days=1, hours=18)).isoformat(), "event": "24h soak period passed. Incident resolved."},
            ],
            "labels": ["network", "infiniband", "transceiver", "hardware"],
            "action_items": [
                {"task": "Audit all QSFP transceivers in KR1B spines", "owner": "NetOps-Park", "status": "in_progress"},
                {"task": "Update transceiver FW to v2.4.0042", "owner": "FW-Team", "status": "planned"},
            ]
        },
        {
            "id": "INC-2026-0308", "title": "PSU Degradation Alert — KR1A Rack A02",
            "severity": "medium", "status": "resolved",
            "service": "Power Infrastructure", "environment": "KR1A Prod",
            "started_at": (now - timedelta(days=5)).isoformat(),
            "mitigated_at": (now - timedelta(days=5, hours=-2)).isoformat(),
            "resolved_at": (now - timedelta(days=4)).isoformat(),
            "commander": "DC-Ops-Lee", "slack_channel": "#inc-power-kr1a-0308",
            "rootly_url": "https://rootly.com/incidents/INC-2026-0308",
            "summary": "PSU redundancy lost on gpu-h200-005 — one of two PSUs reporting voltage out of spec. Proactive replacement scheduled during maintenance window.",
            "affected_nodes": ["gpu-h200-005"],
            "timeline": [
                {"time": (now - timedelta(days=5)).isoformat(), "event": "BMC alert: PSU-B voltage deviation > 5%"},
                {"time": (now - timedelta(days=5, hours=-1)).isoformat(), "event": "Confirmed node still operational on PSU-A (N+1 redundancy intact)"},
                {"time": (now - timedelta(days=4)).isoformat(), "event": "PSU-B replaced during maintenance window"},
            ],
            "labels": ["power", "psu", "hardware", "proactive"],
            "action_items": [
                {"task": "PSU firmware baseline audit across fleet", "owner": "HW-Ops", "status": "done"},
            ]
        },
        {
            "id": "INC-2026-0305", "title": "NVMe SSD SMART Warning — KR1B Staging",
            "severity": "low", "status": "resolved",
            "service": "Storage — NVMe", "environment": "KR1B Staging",
            "started_at": (now - timedelta(days=8)).isoformat(),
            "mitigated_at": (now - timedelta(days=8, hours=-1)).isoformat(),
            "resolved_at": (now - timedelta(days=7)).isoformat(),
            "commander": "SRE-Kim", "slack_channel": "#inc-storage-kr1b-0305",
            "rootly_url": "https://rootly.com/incidents/INC-2026-0305",
            "summary": "SMART pre-failure warning on NVMe slot 3 of gpu-stg-002. Staging node — no customer impact. Drive replaced proactively.",
            "affected_nodes": ["gpu-stg-002"],
            "timeline": [
                {"time": (now - timedelta(days=8)).isoformat(), "event": "SMART alert: Media Wearout Indicator below threshold"},
                {"time": (now - timedelta(days=7)).isoformat(), "event": "NVMe drive replaced and node re-certified"},
            ],
            "labels": ["storage", "nvme", "smart", "proactive"],
            "action_items": []
        },
        {
            "id": "INC-2026-0301", "title": "BCM Cluster Manager Connectivity Loss — KR1A",
            "severity": "critical", "status": "resolved",
            "service": "Cluster Management — BCM", "environment": "KR1A Prod",
            "started_at": (now - timedelta(days=12)).isoformat(),
            "mitigated_at": (now - timedelta(days=12, hours=-1)).isoformat(),
            "resolved_at": (now - timedelta(days=11, hours=12)).isoformat(),
            "commander": "SRE-Choi", "slack_channel": "#inc-bcm-kr1a-0301",
            "rootly_url": "https://rootly.com/incidents/INC-2026-0301",
            "summary": "BCM head node lost connectivity to 15 compute nodes in KR1A due to management switch failover. All nodes recovered automatically after switch stabilized.",
            "affected_nodes": ["gpu-h200-001", "gpu-h200-002", "gpu-h200-003", "gpu-h200-004", "gpu-h200-005"],
            "timeline": [
                {"time": (now - timedelta(days=12)).isoformat(), "event": "BCM heartbeat lost for 15 nodes simultaneously"},
                {"time": (now - timedelta(days=12, hours=-0.5)).isoformat(), "event": "Management switch failover completed"},
                {"time": (now - timedelta(days=12, hours=-1)).isoformat(), "event": "All nodes reconnected to BCM"},
                {"time": (now - timedelta(days=11, hours=12)).isoformat(), "event": "Root cause confirmed: scheduled switch firmware update triggered unexpected failover"},
            ],
            "labels": ["bcm", "management", "network", "switch"],
            "action_items": [
                {"task": "Change management review for switch firmware updates", "owner": "NetOps", "status": "done"},
            ]
        },
    ]
    if resolved is True:
        rootly_incidents = [i for i in rootly_incidents if i["resolved_at"]]
    elif resolved is False:
        rootly_incidents = [i for i in rootly_incidents if not i["resolved_at"]]
    return rootly_incidents


# ── 9. Certifications ──
@app.get("/api/v1/certifications")
def list_certifications(user: str = Depends(auth)):
    nodes = db.list_nodes()
    return [{"node_id": n.id, "type": n.node_type.value,
             "last_certified": n.last_certified.isoformat() if n.last_certified else None,
             "status": n.cert_status, "health_score": n.health_score} for n in nodes]


# ── 10. Rack view ──
@app.get("/api/v1/racks/{rack_id}/nodes")
def rack_nodes(rack_id: str, user: str = Depends(auth)):
    nodes = db.list_nodes()
    return [{"node_id": n.id, "position": n.location.position,
             "type": n.node_type.value, "sku": n.hardware.sku,
             "state": n.state.value, "health": n.health_score,
             "tenant": n.tenant, "cordon_owner": n.cordon.owner}
            for n in nodes if n.location.rack == rack_id]


# ── 11. Tenant nodes ──
@app.get("/api/v1/tenants/{tenant_id}/nodes")
def tenant_nodes(tenant_id: str, user: str = Depends(auth)):
    nodes = db.list_nodes()
    return [_node_to_dict(n) for n in nodes if n.tenant == tenant_id]


# ── 12. Firmware compliance (extended) ──
@app.get("/api/v1/firmware/compliance")
def firmware_compliance(user: str = Depends(auth)):
    nodes = db.list_nodes()
    return [{
        "node_id": n.id, "sku": n.hardware.sku,
        "gpu_driver": n.firmware.gpu_driver, "cuda": n.firmware.cuda,
        "bios": n.firmware.bios, "bmc": n.firmware.bmc, "ofed": n.firmware.ofed,
        "gpu_vbios": n.firmware.gpu_vbios, "nvswitch_fw": n.firmware.nvswitch_fw,
        "cx_fw": n.firmware.cx_fw, "transceiver_fw": n.firmware.transceiver_fw,
        "nvme_fw": n.firmware.nvme_fw, "psu_fw": n.firmware.psu_fw,
        "hgx_fw": n.firmware.hgx_fw, "bf_fw": n.firmware.bf_fw,
    } for n in nodes]


# ── 13. Firmware matrix (grouped by SKU) ──
@app.get("/api/v1/firmware/matrix")
def firmware_matrix(user: str = Depends(auth)):
    nodes = db.list_nodes()
    matrix: dict = {}
    for n in nodes:
        sku = n.hardware.sku
        if sku not in matrix:
            matrix[sku] = {"sku": sku, "count": 0, "firmware_versions": {}}
        matrix[sku]["count"] += 1
        fw = matrix[sku]["firmware_versions"]
        for field in ["gpu_driver", "cuda", "bios", "bmc", "ofed", "gpu_vbios",
                      "nvswitch_fw", "cx_fw", "transceiver_fw", "nvme_fw",
                      "psu_fw", "hgx_fw", "bf_fw"]:
            val = getattr(n.firmware, field, "")
            if val:
                fw.setdefault(field, set()).add(val)
    # Convert sets to lists for JSON serialization
    for sku_data in matrix.values():
        sku_data["firmware_versions"] = {k: sorted(v)
                                          for k, v in sku_data["firmware_versions"].items()}
    return list(matrix.values())


# ── 14. Node BOM ──
@app.get("/api/v1/nodes/{node_id}/bom")
def node_bom(node_id: str, user: str = Depends(auth)):
    node = db.get_node(node_id)
    if not node:
        raise HTTPException(404, f"Node {node_id} not found")
    bom = get_bom_template(node.hardware.sku)
    # Populate firmware versions from node
    for comp in bom.components:
        if comp.firmware_field:
            comp.firmware_version = getattr(node.firmware, comp.firmware_field, "")
    return {
        "node_id": node_id,
        "platform": bom.platform,
        "sku": node.hardware.sku,
        "serial": node.hardware.serial,
        "components": [
            {"category": c.category, "part_name": c.part_name,
             "part_number": c.part_number, "quantity": c.quantity,
             "firmware_field": c.firmware_field,
             "firmware_version": c.firmware_version}
            for c in bom.components
        ],
    }


# ── 15. Network health ──
@app.get("/api/v1/health/network")
def network_health(user: str = Depends(auth)):
    nodes = db.list_nodes()
    return [{"node_id": n.id, "ib_ports": n.hardware.ib_ports,
             "switch": n.location.switch, "switch_port": n.location.switch_port,
             "health_score": n.health_score, "state": n.state.value}
            for n in nodes if n.hardware.ib_ports > 0]


# ── 16. Health summary ──
@app.get("/api/v1/health/summary")
def health_summary(user: str = Depends(auth)):
    cap = db.get_fleet_capacity()
    nodes = db.list_nodes()
    avg_health = sum(n.health_score for n in nodes) / len(nodes) if nodes else 0
    return {
        "total_nodes": cap["total"],
        "average_health_score": round(avg_health, 2),
        "by_state": cap["by_state"], "by_az": cap["by_az"],
        "by_type": cap["by_type"], "by_sku": cap.get("by_sku", {}),
    }


# ── 17. Alerts ──
@app.get("/api/v1/alerts")
def recent_alerts(limit: int = 20, user: str = Depends(auth)):
    return get_recent_alerts(limit)


# ── 18. Classifier rules ──
@app.get("/api/v1/classifier/rules")
def classifier_rules(user: str = Depends(auth)):
    return [{"id": r["id"], "event": r["event"], "class": r["class"].value,
             "confidence": r["confidence"], "severity": r["severity"].value,
             "action": r["action"], "route_to": r["route"]} for r in RULES]


# ── 19. Events ──
@app.get("/api/v1/events")
def list_events(node_id: Optional[str] = None, limit: int = 50,
                user: str = Depends(auth)):
    return db.list_events(node_id=node_id, limit=limit)


# ── 20-21. NetBox mock ──
@app.get("/api/v1/netbox/racks")
def netbox_racks(user: str = Depends(auth)):
    nodes = db.list_nodes()
    racks: dict[str, list] = {}
    for n in nodes:
        r = n.location.rack
        if r not in racks:
            racks[r] = []
        racks[r].append({
            "position": n.location.position, "node_id": n.id,
            "type": n.node_type.value, "sku": n.hardware.sku,
            "nlm_state": n.state.value, "nlm_health": n.health_score,
            "nlm_tenant": n.tenant, "nlm_cordon_owner": n.cordon.owner,
        })
    return {r: sorted(devs, key=lambda x: x["position"])
            for r, devs in sorted(racks.items())}


@app.get("/api/v1/netbox/devices")
def netbox_devices(user: str = Depends(auth)):
    nodes = db.list_nodes()
    return [{"id": n.id, "fqdn": n.fqdn, "rack": n.location.rack,
             "position": n.location.position, "sku": n.hardware.sku,
             "serial": n.hardware.serial, "type": n.node_type.value,
             "nlm_state": n.state.value, "nlm_health": n.health_score,
             "nlm_tenant": n.tenant, "nlm_cordon_owner": n.cordon.owner,
             "nlm_last_cert": n.last_certified.isoformat() if n.last_certified else None}
            for n in nodes]


# ── 22. Auth check endpoint ──
@app.get("/api/v1/auth/check")
def auth_check(user: str = Depends(auth)):
    return {"authenticated": True, "user": user}


# ── 23. Topology (hierarchical: region > AZ > rack > devices) ──
@app.get("/api/v1/topology")
def topology(user: str = Depends(auth)):
    nodes = db.list_nodes()
    tree: dict = {}
    for n in nodes:
        region = "ap-korea-1"
        az = n.location.az or "unknown"
        rack = n.location.rack or "unassigned"
        tree.setdefault(region, {}).setdefault(az, {}).setdefault(rack, []).append({
            "id": n.id, "type": n.node_type.value, "sku": n.hardware.sku,
            "state": n.state.value, "health": n.health_score,
            "power_kw": n.hardware.power_draw_kw, "tenant": n.tenant,
            "cordon": n.cordon.is_cordoned, "cordon_reason": n.cordon.reason,
            "gpu_count": n.hardware.gpu_count, "position": n.location.position,
        })
    result = []
    for region, azs in sorted(tree.items()):
        az_list = []
        for az_name, racks in sorted(azs.items()):
            rack_list = []
            for rack_name, devices in sorted(racks.items()):
                total_power = sum(d["power_kw"] for d in devices)
                rack_list.append({
                    "rack": rack_name, "device_count": len(devices),
                    "total_power_kw": round(total_power, 1),
                    "gpus": sum(d["gpu_count"] for d in devices),
                    "healthy": sum(1 for d in devices if d["health"] >= 0.8),
                    "devices": sorted(devices, key=lambda d: d["position"]),
                })
            total_nodes = sum(r["device_count"] for r in rack_list)
            total_power = sum(r["total_power_kw"] for r in rack_list)
            total_gpus = sum(r["gpus"] for r in rack_list)
            az_list.append({
                "az": az_name, "rack_count": len(rack_list),
                "node_count": total_nodes, "total_power_kw": round(total_power, 1),
                "total_gpus": total_gpus,
                "healthy": sum(r["healthy"] for r in rack_list),
                "racks": rack_list,
            })
        result.append({
            "region": region,
            "az_count": len(az_list),
            "node_count": sum(a["node_count"] for a in az_list),
            "total_power_kw": round(sum(a["total_power_kw"] for a in az_list), 1),
            "total_gpus": sum(a["total_gpus"] for a in az_list),
            "azs": az_list,
        })
    return result


# ── 24. Power summary ──
@app.get("/api/v1/power/summary")
def power_summary(user: str = Depends(auth)):
    nodes = db.list_nodes()
    racks: dict = {}
    for n in nodes:
        r = n.location.rack
        if r not in racks:
            racks[r] = {"rack": r, "az": n.location.az, "environment": n.location.environment,
                        "power_kw": 0, "node_count": 0, "gpu_count": 0}
        racks[r]["power_kw"] += n.hardware.power_draw_kw
        racks[r]["node_count"] += 1
        racks[r]["gpu_count"] += n.hardware.gpu_count
    total = sum(r["power_kw"] for r in racks.values())
    return {
        "total_power_kw": round(total, 1),
        "racks": sorted(racks.values(), key=lambda x: -x["power_kw"]),
    }


def _node_to_dict(n) -> dict:
    return {
        "id": n.id, "fqdn": n.fqdn, "type": n.node_type.value,
        "state": n.state.value,
        "state_since": n.state_since.isoformat() if n.state_since else None,
        "state_reason": n.state_reason, "state_owner": n.state_owner,
        "az": n.location.az, "environment": n.location.environment,
        "rack": n.location.rack, "position": n.location.position,
        "pdu": n.location.pdu, "switch": n.location.switch,
        "sku": n.hardware.sku, "serial": n.hardware.serial,
        "gpu_model": n.hardware.gpu_model, "gpu_count": n.hardware.gpu_count,
        "cpu_model": n.hardware.cpu_model, "cpu_cores": n.hardware.cpu_cores,
        "ram_gb": n.hardware.ram_gb, "power_draw_kw": n.hardware.power_draw_kw,
        "backend": n.backend.value,
        "cordon": {"active": n.cordon.is_cordoned, "owner": n.cordon.owner,
                   "priority": n.cordon.priority.value, "reason": n.cordon.reason},
        "tenant": n.tenant, "customer_protected": n.customer_protected,
        "health_score": n.health_score,
        "last_certified": n.last_certified.isoformat() if n.last_certified else None,
        "cert_status": n.cert_status,
        "firmware": {
            "gpu_driver": n.firmware.gpu_driver, "cuda": n.firmware.cuda,
            "bios": n.firmware.bios, "bmc": n.firmware.bmc, "ofed": n.firmware.ofed,
            "gpu_vbios": n.firmware.gpu_vbios, "nvswitch_fw": n.firmware.nvswitch_fw,
            "cx_fw": n.firmware.cx_fw, "transceiver_fw": n.firmware.transceiver_fw,
            "nvme_fw": n.firmware.nvme_fw, "psu_fw": n.firmware.psu_fw,
            "hgx_fw": n.firmware.hgx_fw, "bf_fw": n.firmware.bf_fw,
        },
    }


# ── Operator Manager ──────────────────────────────────────────────
op_manager = OperatorManager()
op_manager.register(Reconciler(interval=60))
op_manager.register(MaintenanceOrchestrator(interval=120))
op_manager.register(TestingScheduler(interval=300, mock_mode=True))


@app.on_event("startup")
async def startup():
    gitops.seed_default_policies()
    await op_manager.start_all()


@app.on_event("shutdown")
async def shutdown():
    await op_manager.stop_all()


# ── 25. Operator status (READ) ──
@app.get("/api/v1/operators/status")
def operator_status(user: str = Depends(auth)):
    return op_manager.status()


# ── 26. Trigger operator (emergency write, operator only) ──
@app.post("/api/v1/operators/{name}/trigger")
async def trigger_operator(name: str, user: str = Depends(auth)):
    op = op_manager.get(name)
    if not op:
        raise HTTPException(404, f"Operator '{name}' not found")
    result = await op.trigger()
    return {"operator": name, "result": result}


# ── 27. Toggle operator ──
@app.post("/api/v1/operators/{name}/toggle")
def toggle_operator(name: str, enabled: bool = True, user: str = Depends(auth)):
    op = op_manager.get(name)
    if not op:
        raise HTTPException(404, f"Operator '{name}' not found")
    op.toggle(enabled)
    return {"operator": name, "enabled": enabled}


# ── 28. GitOps desired-state list (READ) ──
@app.get("/api/v1/gitops/desired-states")
def gitops_desired_states(user: str = Depends(auth)):
    return gitops.list_desired_states()


# ── 29. GitOps cordons list (READ) ──
@app.get("/api/v1/gitops/cordons")
def gitops_cordons(user: str = Depends(auth)):
    return gitops.list_cordons()


# ── 30. GitOps policies (READ) ──
@app.get("/api/v1/gitops/policies")
def gitops_policies(user: str = Depends(auth)):
    policies = {}
    for name in ("health-thresholds", "test-schedule", "firmware-baseline"):
        p = gitops.read_policy(name)
        if p:
            policies[name] = p
    return policies


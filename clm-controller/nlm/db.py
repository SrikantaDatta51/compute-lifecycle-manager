"""NLM SQLite Database — full CRUD for nodes, events, incidents, certifications."""
from __future__ import annotations
import json
import sqlite3
import os
from datetime import datetime, timezone
from typing import Optional
from .models import (
    Node, NodeState, NodeType, BackendType, CordonPriority,
    Location, Hardware, Firmware, CordonInfo,
    StateTransitionEvent, Incident, AlertEvent, Severity,
)

DB_PATH = os.environ.get("NLM_DB_PATH", "nlm-data/nlm.db")


def _connect(path: str | None = None) -> sqlite3.Connection:
    p = path or DB_PATH
    os.makedirs(os.path.dirname(p), exist_ok=True)
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(path: str | None = None):
    conn = _connect(path)
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS nodes (
        id TEXT PRIMARY KEY,
        fqdn TEXT,
        node_type TEXT DEFAULT 'gpu',
        state TEXT DEFAULT 'provisioning',
        state_since TEXT,
        state_reason TEXT DEFAULT '',
        state_owner TEXT DEFAULT '',
        az TEXT DEFAULT '',
        environment TEXT DEFAULT '',
        rack TEXT DEFAULT '',
        rack_position INTEGER DEFAULT 0,
        pdu TEXT DEFAULT '',
        switch TEXT DEFAULT '',
        switch_port TEXT DEFAULT '',
        sku TEXT DEFAULT '',
        serial TEXT DEFAULT '',
        gpu_model TEXT DEFAULT '',
        gpu_count INTEGER DEFAULT 0,
        cpu_model TEXT DEFAULT '',
        cpu_cores INTEGER DEFAULT 0,
        ram_gb INTEGER DEFAULT 0,
        nvme_count INTEGER DEFAULT 0,
        ib_ports INTEGER DEFAULT 0,
        power_draw_kw REAL DEFAULT 0.0,
        bios TEXT DEFAULT '',
        bmc TEXT DEFAULT '',
        gpu_driver TEXT DEFAULT '',
        cuda TEXT DEFAULT '',
        ofed TEXT DEFAULT '',
        gpu_vbios TEXT DEFAULT '',
        nvswitch_fw TEXT DEFAULT '',
        cx_fw TEXT DEFAULT '',
        transceiver_fw TEXT DEFAULT '',
        nvme_fw TEXT DEFAULT '',
        psu_fw TEXT DEFAULT '',
        hgx_fw TEXT DEFAULT '',
        bf_fw TEXT DEFAULT '',
        cordon_active INTEGER DEFAULT 0,
        cordon_owner TEXT DEFAULT '',
        cordon_priority TEXT DEFAULT 'P4',
        cordon_reason TEXT DEFAULT '',
        cordon_since TEXT,
        backend TEXT DEFAULT 'bcm',
        tenant TEXT DEFAULT '',
        customer_protected INTEGER DEFAULT 0,
        health_score REAL DEFAULT 1.0,
        last_certified TEXT,
        cert_status TEXT DEFAULT '',
        tags TEXT DEFAULT '{}',
        created_at TEXT,
        updated_at TEXT
    );

    CREATE TABLE IF NOT EXISTS events (
        id TEXT PRIMARY KEY,
        node_id TEXT,
        from_state TEXT,
        to_state TEXT,
        trigger_name TEXT,
        owner TEXT DEFAULT '',
        priority TEXT DEFAULT 'P4',
        timestamp TEXT,
        success INTEGER DEFAULT 1,
        error TEXT DEFAULT '',
        metadata TEXT DEFAULT '{}'
    );

    CREATE TABLE IF NOT EXISTS incidents (
        id TEXT PRIMARY KEY,
        incident_type TEXT,
        affected_nodes TEXT DEFAULT '[]',
        classification TEXT DEFAULT 'unknown',
        severity TEXT DEFAULT 'high',
        route_to TEXT DEFAULT '',
        created_at TEXT,
        resolved INTEGER DEFAULT 0,
        details TEXT DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS alerts (
        id TEXT PRIMARY KEY,
        node_id TEXT,
        severity TEXT,
        channel TEXT,
        message TEXT,
        timestamp TEXT,
        acknowledged INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS netbox_devices (
        id TEXT PRIMARY KEY,
        node_id TEXT,
        rack TEXT,
        position INTEGER,
        device_type TEXT,
        nlm_state TEXT,
        nlm_health REAL DEFAULT 1.0,
        nlm_tenant TEXT DEFAULT '',
        nlm_cordon_owner TEXT DEFAULT '',
        nlm_last_cert TEXT DEFAULT '',
        updated_at TEXT
    );
    """)
    conn.commit()
    conn.close()


def _node_from_row(row: sqlite3.Row) -> Node:
    return Node(
        id=row["id"], fqdn=row["fqdn"] or "",
        node_type=NodeType(row["node_type"]),
        state=NodeState(row["state"]),
        state_since=datetime.fromisoformat(row["state_since"]) if row["state_since"] else None,
        state_reason=row["state_reason"] or "",
        state_owner=row["state_owner"] or "",
        location=Location(
            az=row["az"] or "", environment=row["environment"] or "",
            rack=row["rack"] or "", position=row["rack_position"] or 0,
            pdu=row["pdu"] or "", switch=row["switch"] or "",
            switch_port=row["switch_port"] or "",
        ),
        hardware=Hardware(
            sku=row["sku"] or "", serial=row["serial"] or "",
            gpu_model=row["gpu_model"] or "", gpu_count=row["gpu_count"] or 0,
            cpu_model=row["cpu_model"] or "", cpu_cores=row["cpu_cores"] or 0,
            ram_gb=row["ram_gb"] or 0, nvme_count=row["nvme_count"] or 0,
            ib_ports=row["ib_ports"] or 0, power_draw_kw=row["power_draw_kw"] or 0.0,
        ),
        firmware=Firmware(
            bios=row["bios"] or "", bmc=row["bmc"] or "",
            gpu_driver=row["gpu_driver"] or "", cuda=row["cuda"] or "",
            ofed=row["ofed"] or "",
            gpu_vbios=row["gpu_vbios"] or "", nvswitch_fw=row["nvswitch_fw"] or "",
            cx_fw=row["cx_fw"] or "", transceiver_fw=row["transceiver_fw"] or "",
            nvme_fw=row["nvme_fw"] or "", psu_fw=row["psu_fw"] or "",
            hgx_fw=row["hgx_fw"] or "", bf_fw=row["bf_fw"] or "",
        ),
        cordon=CordonInfo(
            is_cordoned=bool(row["cordon_active"]),
            owner=row["cordon_owner"] or "",
            priority=CordonPriority(row["cordon_priority"]) if row["cordon_priority"] else CordonPriority.P4,
            reason=row["cordon_reason"] or "",
            since=datetime.fromisoformat(row["cordon_since"]) if row["cordon_since"] else None,
        ),
        backend=BackendType(row["backend"]),
        tenant=row["tenant"] or "",
        customer_protected=bool(row["customer_protected"]),
        health_score=row["health_score"] or 1.0,
        last_certified=datetime.fromisoformat(row["last_certified"]) if row["last_certified"] else None,
        cert_status=row["cert_status"] or "",
        tags=json.loads(row["tags"]) if row["tags"] else {},
        created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
        updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
    )


def save_node(node: Node, path: str | None = None):
    conn = _connect(path)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("""
    INSERT OR REPLACE INTO nodes VALUES (
        ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
    )""", (
        node.id, node.fqdn, node.node_type.value, node.state.value,
        node.state_since.isoformat() if node.state_since else now,
        node.state_reason, node.state_owner,
        node.location.az, node.location.environment, node.location.rack,
        node.location.position, node.location.pdu, node.location.switch,
        node.location.switch_port,
        node.hardware.sku, node.hardware.serial, node.hardware.gpu_model,
        node.hardware.gpu_count, node.hardware.cpu_model, node.hardware.cpu_cores,
        node.hardware.ram_gb, node.hardware.nvme_count, node.hardware.ib_ports,
        node.hardware.power_draw_kw,
        node.firmware.bios, node.firmware.bmc, node.firmware.gpu_driver,
        node.firmware.cuda, node.firmware.ofed,
        node.firmware.gpu_vbios, node.firmware.nvswitch_fw, node.firmware.cx_fw,
        node.firmware.transceiver_fw, node.firmware.nvme_fw, node.firmware.psu_fw,
        node.firmware.hgx_fw, node.firmware.bf_fw,
        int(node.cordon.is_cordoned), node.cordon.owner, node.cordon.priority.value,
        node.cordon.reason, node.cordon.since.isoformat() if node.cordon.since else None,
        node.backend.value, node.tenant, int(node.customer_protected),
        node.health_score,
        node.last_certified.isoformat() if node.last_certified else None,
        node.cert_status, json.dumps(node.tags),
        node.created_at.isoformat() if node.created_at else now,
        now,
    ))
    conn.commit()
    conn.close()


def get_node(node_id: str, path: str | None = None) -> Optional[Node]:
    conn = _connect(path)
    row = conn.execute("SELECT * FROM nodes WHERE id=?", (node_id,)).fetchone()
    conn.close()
    return _node_from_row(row) if row else None


def list_nodes(state: str | None = None, az: str | None = None,
               node_type: str | None = None, backend: str | None = None,
               path: str | None = None) -> list[Node]:
    conn = _connect(path)
    q = "SELECT * FROM nodes WHERE 1=1"
    params: list = []
    if state:
        q += " AND state=?"; params.append(state)
    if az:
        q += " AND az=?"; params.append(az)
    if node_type:
        q += " AND node_type=?"; params.append(node_type)
    if backend:
        q += " AND backend=?"; params.append(backend)
    q += " ORDER BY id"
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [_node_from_row(r) for r in rows]


def save_event(event: StateTransitionEvent, path: str | None = None):
    conn = _connect(path)
    conn.execute("""
    INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, (
        event.id, event.node_id, event.from_state.value, event.to_state.value,
        event.trigger, event.owner, event.priority.value,
        event.timestamp.isoformat(), int(event.success), event.error,
        json.dumps(event.metadata),
    ))
    conn.commit()
    conn.close()


def list_events(node_id: str | None = None, limit: int = 50,
                path: str | None = None) -> list[dict]:
    conn = _connect(path)
    if node_id:
        rows = conn.execute(
            "SELECT * FROM events WHERE node_id=? ORDER BY timestamp DESC LIMIT ?",
            (node_id, limit)).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM events ORDER BY timestamp DESC LIMIT ?",
            (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_incident(inc: Incident, path: str | None = None):
    conn = _connect(path)
    conn.execute("""
    INSERT OR REPLACE INTO incidents VALUES (?,?,?,?,?,?,?,?,?)
    """, (
        inc.id, inc.incident_type, json.dumps(inc.affected_nodes),
        inc.classification.value, inc.severity.value, inc.route_to,
        inc.created_at.isoformat(), int(inc.resolved), inc.details,
    ))
    conn.commit()
    conn.close()


def list_incidents(resolved: bool | None = None,
                   path: str | None = None) -> list[dict]:
    conn = _connect(path)
    if resolved is not None:
        rows = conn.execute(
            "SELECT * FROM incidents WHERE resolved=? ORDER BY created_at DESC",
            (int(resolved),)).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM incidents ORDER BY created_at DESC").fetchall()
    conn.close()
    results = []
    for r in rows:
        d = dict(r)
        d["affected_nodes"] = json.loads(d["affected_nodes"])
        results.append(d)
    return results


def save_alert(alert: AlertEvent, path: str | None = None):
    conn = _connect(path)
    conn.execute("""
    INSERT INTO alerts VALUES (?,?,?,?,?,?,?)
    """, (
        alert.id, alert.node_id, alert.severity.value, alert.channel,
        alert.message, alert.timestamp.isoformat(), int(alert.acknowledged),
    ))
    conn.commit()
    conn.close()


def get_fleet_capacity(path: str | None = None) -> dict:
    conn = _connect(path)
    rows = conn.execute("""
    SELECT state, node_type, az, sku, COUNT(*) as count
    FROM nodes GROUP BY state, node_type, az, sku ORDER BY state, node_type
    """).fetchall()
    conn.close()
    result = {"total": 0, "by_state": {}, "by_type": {}, "by_az": {}, "by_sku": {}, "details": []}
    for r in rows:
        d = dict(r)
        result["details"].append(d)
        result["total"] += d["count"]
        result["by_state"][d["state"]] = result["by_state"].get(d["state"], 0) + d["count"]
        result["by_type"][d["node_type"]] = result["by_type"].get(d["node_type"], 0) + d["count"]
        result["by_az"][d["az"]] = result["by_az"].get(d["az"], 0) + d["count"]
        result["by_sku"][d["sku"]] = result["by_sku"].get(d["sku"], 0) + d["count"]
    return result

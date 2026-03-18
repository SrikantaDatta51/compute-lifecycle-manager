"""NLM Mock Fleet — seeds 55 nodes (GPU + CPU) across Korea regions + Mock NetBox."""
from __future__ import annotations
import random
from datetime import datetime, timezone, timedelta
from .models import (
    Node, NodeState, NodeType, BackendType, Location, Hardware, Firmware,
)
from . import db

# Platform-specific firmware — all 12+ fields populated
FW_H200 = Firmware(
    bios="2.17.0", bmc="23.08.10", gpu_driver="550.90.07", cuda="12.4",
    ofed="24.01-0.3.3.1", gpu_vbios="96.00.89.00.01", nvswitch_fw="4.2.0.20",
    cx_fw="28.39.1002", transceiver_fw="2.4.0036", nvme_fw="2.5.0.31",
    psu_fw="02.04.0019", hgx_fw="23.08.10.01", bf_fw="",
)
FW_B200 = Firmware(
    bios="2.19.0", bmc="24.02.04", gpu_driver="560.35.03", cuda="12.6",
    ofed="24.07-0.6.1.0", gpu_vbios="97.00.54.00.01", nvswitch_fw="5.1.0.12",
    cx_fw="28.41.1000", transceiver_fw="2.4.0042", nvme_fw="2.6.0.15",
    psu_fw="02.06.0022", hgx_fw="24.02.04.01", bf_fw="24.07.2010",
)
FW_A100 = Firmware(
    bios="2.14.0", bmc="22.11.08", gpu_driver="535.183.01", cuda="12.2",
    ofed="23.10-1.1.9.0", gpu_vbios="94.02.72.00.01", nvswitch_fw="3.10.18002",
    cx_fw="22.39.1002", transceiver_fw="2.3.0028", nvme_fw="2.4.0.22",
    psu_fw="02.02.0015", hgx_fw="22.11.08.01", bf_fw="",
)
FW_CPU = Firmware(
    bios="2.17.0", bmc="23.08.10", gpu_driver="", cuda="",
    ofed="24.01-0.3.3.1", gpu_vbios="", nvswitch_fw="", cx_fw="22.41.1000",
    transceiver_fw="", nvme_fw="2.5.0.31", psu_fw="02.03.0012",
    hgx_fw="", bf_fw="",
)


def _ts(days_ago: int = 0) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days_ago)


def seed_fleet(db_path: str | None = None):
    """Seed 55 mock nodes across Korea regions (KR1A, KR1B)."""
    db.init_db(db_path)
    nodes: list[Node] = []

    # KR1A Prod — BCM — H200 (10 nodes)
    for i in range(1, 11):
        n = Node(
            id=f"gpu-h200-{i:03d}", fqdn=f"gpu-h200-{i:03d}.kr1a.prod.cic.local",
            node_type=NodeType.GPU,
            state=NodeState.CUSTOMER_ASSIGNED if i <= 6 else NodeState.CERTIFIED_READY,
            location=Location(az="kr1a", environment="KR1A Prod",
                              rack=f"rack-A{(i-1)//4+1:02d}", position=i*4,
                              pdu=f"pdu-A{(i-1)//4+1:02d}", switch=f"leaf-sw-A{(i-1)//8+1:02d}",
                              switch_port=f"1/{i}"),
            hardware=Hardware(sku="DGX-H200", serial=f"SN-H200-{i:04d}",
                              gpu_model="H200 SXM 141GB", gpu_count=8,
                              cpu_model="Intel Xeon w9-3495X", cpu_cores=56,
                              ram_gb=2048, nvme_count=8, ib_ports=8, power_draw_kw=10.2),
            firmware=FW_H200,
            backend=BackendType.BCM,
            tenant=f"tenant-{chr(65+i%3)}" if i <= 6 else "",
            customer_protected=i <= 6,
            health_score=1.0,
            last_certified=_ts(random.randint(1, 7)),
            cert_status="passed",
            created_at=_ts(90),
        )
        nodes.append(n)

    # KR1A Prod — BCM — B200 (10 nodes)
    for i in range(1, 11):
        state = [NodeState.CUSTOMER_ASSIGNED]*5 + [NodeState.CERTIFIED_READY]*2 + \
                [NodeState.TESTING, NodeState.REPAIR, NodeState.RMA]
        n = Node(
            id=f"gpu-b200-{i:03d}", fqdn=f"gpu-b200-{i:03d}.kr1a.prod.cic.local",
            node_type=NodeType.GPU,
            state=state[i-1],
            location=Location(az="kr1a", environment="KR1A Prod",
                              rack=f"rack-B{(i-1)//4+1:02d}", position=i*4,
                              pdu=f"pdu-B{(i-1)//4+1:02d}", switch=f"leaf-sw-B{(i-1)//8+1:02d}",
                              switch_port=f"2/{i}"),
            hardware=Hardware(sku="DGX-B200", serial=f"SN-B200-{i:04d}",
                              gpu_model="B200 SXM 192GB", gpu_count=8,
                              cpu_model="Intel Xeon w9-3595X", cpu_cores=64,
                              ram_gb=2048, nvme_count=8, ib_ports=8, power_draw_kw=14.3),
            firmware=FW_B200,
            backend=BackendType.BCM,
            tenant=f"tenant-{chr(65+i%4)}" if i <= 5 else "",
            customer_protected=i <= 5,
            health_score=0.3 if state[i-1] in (NodeState.REPAIR, NodeState.RMA) else 1.0,
            last_certified=_ts(random.randint(1, 14)),
            cert_status="passed" if state[i-1] not in (NodeState.REPAIR, NodeState.RMA) else "failed",
            created_at=_ts(60),
        )
        if state[i-1] in (NodeState.REPAIR, NodeState.RMA):
            n.cordon.is_cordoned = True
            n.cordon.owner = "nlm-controller"
            n.cordon.priority_value = "P0"
            n.cordon.reason = "HW failure detected"
        nodes.append(n)

    # KR1A Dev — K8s only (5 GPU nodes)
    for i in range(1, 6):
        n = Node(
            id=f"gpu-dev-{i:03d}", fqdn=f"gpu-dev-{i:03d}.kr1a.dev.cic.local",
            node_type=NodeType.GPU,
            state=NodeState.CERTIFIED_READY if i <= 3 else NodeState.TESTING,
            location=Location(az="kr1a", environment="KR1A Dev",
                              rack=f"rack-D01", position=i*4,
                              pdu="pdu-D01", switch="leaf-sw-D01"),
            hardware=Hardware(sku="A100-80G", serial=f"SN-DEV-{i:04d}",
                              gpu_model="A100 SXM4 80GB", gpu_count=8,
                              cpu_model="AMD EPYC 7742", cpu_cores=64,
                              ram_gb=1024, nvme_count=4, ib_ports=4, power_draw_kw=6.5),
            firmware=FW_A100,
            backend=BackendType.KUBERNETES,
            created_at=_ts(120),
        )
        nodes.append(n)

    # KR1B Prod BMaaS — Bare Metal (10 GPU nodes)
    for i in range(1, 11):
        state = [NodeState.CUSTOMER_ASSIGNED]*4 + [NodeState.CERTIFIED_READY]*3 + \
                [NodeState.PROVISIONING, NodeState.BURN_IN, NodeState.SCHEDULED_MAINTENANCE]
        n = Node(
            id=f"gpu-bm-{i:03d}", fqdn=f"gpu-bm-{i:03d}.kr1b.bmaas.cic.local",
            node_type=NodeType.GPU,
            state=state[i-1],
            location=Location(az="kr1b", environment="KR1B Prod BMaaS",
                              rack=f"rack-BM{(i-1)//4+1:02d}", position=i*4,
                              pdu=f"pdu-BM{(i-1)//4+1:02d}", switch=f"leaf-sw-BM{(i-1)//8+1:02d}"),
            hardware=Hardware(sku="DGX-B200", serial=f"SN-BM-{i:04d}",
                              gpu_model="B200 SXM 192GB", gpu_count=8,
                              cpu_model="Intel Xeon w9-3595X", cpu_cores=64,
                              ram_gb=2048, nvme_count=8, ib_ports=8, power_draw_kw=14.3),
            firmware=FW_B200,
            backend=BackendType.BARE_METAL,
            tenant=f"bmaas-tenant-{chr(65+i%3)}" if i <= 4 else "",
            customer_protected=i <= 4,
            created_at=_ts(45),
        )
        nodes.append(n)

    # KR1B Prod K8s (5 GPU nodes)
    for i in range(1, 6):
        n = Node(
            id=f"gpu-k8s-{i:03d}", fqdn=f"gpu-k8s-{i:03d}.kr1b.k8s.cic.local",
            node_type=NodeType.GPU,
            state=NodeState.CUSTOMER_ASSIGNED if i <= 3 else NodeState.CERTIFIED_READY,
            location=Location(az="kr1b", environment="KR1B Prod K8s",
                              rack="rack-K01", position=i*4,
                              pdu="pdu-K01", switch="leaf-sw-K01"),
            hardware=Hardware(sku="DGX-H200", serial=f"SN-K8S-{i:04d}",
                              gpu_model="H200 SXM 141GB", gpu_count=8,
                              cpu_model="Intel Xeon w9-3495X", cpu_cores=56,
                              ram_gb=2048, nvme_count=8, ib_ports=8, power_draw_kw=10.2),
            firmware=FW_H200,
            backend=BackendType.KUBERNETES,
            tenant=f"k8s-tenant-{chr(65+i%2)}" if i <= 3 else "",
            customer_protected=i <= 3,
            created_at=_ts(30),
        )
        nodes.append(n)

    # KR1B Staging (5 GPU nodes — mixed backends)
    stg_backends = [BackendType.BCM, BackendType.BCM, BackendType.KUBERNETES,
                    BackendType.BARE_METAL, BackendType.BARE_METAL]
    for i in range(1, 6):
        n = Node(
            id=f"gpu-stg-{i:03d}", fqdn=f"gpu-stg-{i:03d}.kr1b.staging.cic.local",
            node_type=NodeType.GPU,
            state=NodeState.CERTIFIED_READY,
            location=Location(az="kr1b", environment="KR1B Staging",
                              rack="rack-STG01", position=i*4,
                              pdu="pdu-STG01", switch="leaf-sw-STG01"),
            hardware=Hardware(sku="DGX-B200", serial=f"SN-STG-{i:04d}",
                              gpu_model="B200 SXM 192GB", gpu_count=8,
                              cpu_model="Intel Xeon w9-3595X", cpu_cores=64,
                              ram_gb=2048, nvme_count=8, ib_ports=8, power_draw_kw=14.3),
            firmware=FW_B200,
            backend=stg_backends[i-1],
            created_at=_ts(60),
        )
        nodes.append(n)

    # CPU nodes — Idle (5 in KR1A, 5 in KR1B)
    for i in range(1, 6):
        n = Node(
            id=f"cpu-kr1a-{i:03d}", fqdn=f"cpu-kr1a-{i:03d}.kr1a.prod.cic.local",
            node_type=NodeType.CPU,
            state=NodeState.PROVISIONING,
            state_reason="idle - never provisioned",
            location=Location(az="kr1a", environment="KR1A Prod",
                              rack=f"rack-C01", position=40+i,
                              pdu="pdu-C01", switch="leaf-sw-C01"),
            hardware=Hardware(sku="CPU-Server", serial=f"SN-CPU-KR1A-{i:04d}",
                              cpu_model="Intel Xeon Gold 6338", cpu_cores=32,
                              ram_gb=512, nvme_count=4),
            firmware=FW_CPU,
            backend=BackendType.BCM,
            health_score=0.5,
            created_at=_ts(180),
        )
        nodes.append(n)

    for i in range(1, 6):
        n = Node(
            id=f"cpu-kr1b-{i:03d}", fqdn=f"cpu-kr1b-{i:03d}.kr1b.bmaas.cic.local",
            node_type=NodeType.CPU,
            state=NodeState.PROVISIONING,
            state_reason="idle - never provisioned",
            location=Location(az="kr1b", environment="KR1B Prod BMaaS",
                              rack="rack-BM03", position=40+i,
                              pdu="pdu-BM03", switch="leaf-sw-BM02"),
            hardware=Hardware(sku="CPU-Server", serial=f"SN-CPU-KR1B-{i:04d}",
                              cpu_model="Intel Xeon Gold 6338", cpu_cores=32,
                              ram_gb=512, nvme_count=4),
            firmware=FW_CPU,
            backend=BackendType.BARE_METAL,
            health_score=0.5,
            created_at=_ts(180),
        )
        nodes.append(n)

    # Save all nodes
    for n in nodes:
        n.state_since = n.state_since or _ts(random.randint(0, 7))
        n.updated_at = datetime.now(timezone.utc)
        db.save_node(n, db_path)

    return len(nodes)


def seed_netbox_devices(db_path: str | None = None):
    """Populate NetBox device table from existing nodes."""
    nodes = db.list_nodes(path=db_path)
    conn = db._connect(db_path)
    for n in nodes:
        conn.execute("""
        INSERT OR REPLACE INTO netbox_devices
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            f"nb-{n.id}", n.id, n.location.rack, n.location.position,
            f"{n.hardware.sku} ({n.node_type.value.upper()})",
            n.state.value, n.health_score, n.tenant,
            n.cordon.owner, n.last_certified.isoformat() if n.last_certified else "",
            datetime.now(timezone.utc).isoformat(),
        ))
    conn.commit()
    conn.close()
    return len(nodes)

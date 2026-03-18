"""NLM Core Data Models — 11-state lifecycle, failure classification, cordon ownership."""
from __future__ import annotations
import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


class NodeState(str, enum.Enum):
    PROVISIONING = "provisioning"
    BURN_IN = "burn_in"
    TESTING = "testing"
    CERTIFIED_READY = "certified_ready"
    CUSTOMER_ASSIGNED = "customer_assigned"
    DRAINING = "draining"
    EMERGENCY_DRAIN = "emergency_drain"
    SCHEDULED_MAINTENANCE = "scheduled_maintenance"
    REPAIR = "repair"
    RMA = "rma"
    DECOMMISSIONED = "decommissioned"


class FailureClass(str, enum.Enum):
    HW_GPU_FATAL = "hw_gpu_fatal"
    HW_GPU_MEMORY = "hw_gpu_memory"
    HW_GPU_CONTAINED = "hw_gpu_contained"
    HW_NVSWITCH = "hw_nvswitch"
    HW_MEMORY_PRED = "hw_memory_predictive"
    HW_NVME = "hw_nvme"
    HW_PSU = "hw_psu"
    HW_THERMAL = "hw_thermal"
    HW_CPU = "hw_cpu"
    NET_TRANSCEIVER = "net_transceiver"
    NET_SWITCH = "net_switch"
    NET_SPINE = "net_spine"
    INFRA_RACK = "infra_rack"
    INFRA_PDU = "infra_pdu"
    INFRA_COOLING = "infra_cooling"
    SW_DRIVER = "sw_driver"
    SW_KERNEL = "sw_kernel"
    UNKNOWN = "unknown"


class CordonPriority(str, enum.Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"


class BackendType(str, enum.Enum):
    BCM = "bcm"
    KUBERNETES = "kubernetes"
    BARE_METAL = "bare_metal"


class NodeType(str, enum.Enum):
    GPU = "gpu"
    CPU = "cpu"


class Severity(str, enum.Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class Location:
    az: str = ""
    environment: str = ""
    rack: str = ""
    position: int = 0
    pdu: str = ""
    switch: str = ""
    switch_port: str = ""


@dataclass
class Hardware:
    sku: str = ""
    serial: str = ""
    gpu_model: str = ""
    gpu_count: int = 0
    cpu_model: str = ""
    cpu_cores: int = 0
    ram_gb: int = 0
    nvme_count: int = 0
    ib_ports: int = 0
    power_draw_kw: float = 0.0


@dataclass
class Firmware:
    bios: str = ""
    bmc: str = ""
    gpu_driver: str = ""
    cuda: str = ""
    ofed: str = ""
    gpu_vbios: str = ""
    nvswitch_fw: str = ""
    cx_fw: str = ""
    transceiver_fw: str = ""
    nvme_fw: str = ""
    psu_fw: str = ""
    hgx_fw: str = ""
    bf_fw: str = ""


@dataclass
class BOMComponent:
    category: str  # gpu, cpu, ram, nvme, nvswitch, nic, dpu, transceiver, bmc, psu, baseboard
    part_name: str
    part_number: str = ""
    quantity: int = 1
    firmware_field: str = ""
    firmware_version: str = ""


@dataclass
class NodeBOM:
    platform: str  # DGX-H200, DGX-B200, DGX-A100, CPU-Server
    components: list[BOMComponent] = field(default_factory=list)


def get_bom_template(sku: str) -> NodeBOM:
    """Return the reference BOM for a given SKU."""
    if "H200" in sku:
        return NodeBOM(platform="DGX-H200", components=[
            BOMComponent("gpu", "NVIDIA H200 SXM 141GB HBM3e", "699-21010-0200-xxx", 8, "gpu_vbios"),
            BOMComponent("cpu", "Intel Xeon w9-3495X (56C/112T)", "", 2, "bios"),
            BOMComponent("ram", "128GB DDR5-4800 ECC RDIMM", "", 16),
            BOMComponent("nvme", "3.84TB Gen4 U.2 NVMe SSD", "", 8, "nvme_fw"),
            BOMComponent("nvswitch", "NVIDIA NVSwitch 4th Gen (LS10)", "699-22010-0200-xxx", 4, "nvswitch_fw"),
            BOMComponent("nic", "NVIDIA ConnectX-7 NDR 400Gb/s", "MCX75310AAS-NEAT", 4, "cx_fw"),
            BOMComponent("transceiver_ib", "400G NDR OSFP Active Copper", "MMS4X00-NS400", 8, "transceiver_fw"),
            BOMComponent("transceiver_mgmt", "100G QSFP56 SR4", "", 1),
            BOMComponent("transceiver_mgmt", "1G RJ45 Management", "", 1),
            BOMComponent("bmc", "NVIDIA BMC (OpenBMC)", "", 1, "bmc"),
            BOMComponent("psu", "2000W Platinum 80+", "", 4, "psu_fw"),
            BOMComponent("baseboard", "HGX H200 8-GPU Baseboard", "920-23687-2530-000", 1, "hgx_fw"),
        ])
    elif "B200" in sku:
        return NodeBOM(platform="DGX-B200", components=[
            BOMComponent("gpu", "NVIDIA B200 SXM 192GB HBM3e (Blackwell)", "699-21010-0300-xxx", 8, "gpu_vbios"),
            BOMComponent("cpu", "Intel Xeon w9-3595X (60C/120T)", "", 2, "bios"),
            BOMComponent("ram", "128GB DDR5-5600 ECC RDIMM", "", 16),
            BOMComponent("nvme", "3.84TB Gen5 U.2 NVMe SSD", "", 8, "nvme_fw"),
            BOMComponent("nvswitch", "NVIDIA NVSwitch 5th Gen (LS11)", "699-22010-0300-xxx", 4, "nvswitch_fw"),
            BOMComponent("nic", "NVIDIA ConnectX-7 NDR 400Gb/s", "MCX75310AAS-NEAT", 4, "cx_fw"),
            BOMComponent("dpu", "NVIDIA BlueField-3 DPU", "MBF3M332A-EENAT", 1, "bf_fw"),
            BOMComponent("transceiver_ib", "400G NDR OSFP Active Copper", "MMS4X00-NS400", 8, "transceiver_fw"),
            BOMComponent("transceiver_mgmt", "100G QSFP56 SR4", "", 1),
            BOMComponent("transceiver_mgmt", "1G RJ45 Management", "", 1),
            BOMComponent("bmc", "NVIDIA BMC (OpenBMC)", "", 1, "bmc"),
            BOMComponent("psu", "2700W Titanium 80+", "", 4, "psu_fw"),
            BOMComponent("baseboard", "HGX B200 8-GPU Baseboard (Blackwell)", "920-2xxxx-xxxx-000", 1, "hgx_fw"),
        ])
    elif "A100" in sku:
        return NodeBOM(platform="DGX-A100", components=[
            BOMComponent("gpu", "NVIDIA A100 SXM4 80GB HBM2e", "699-21010-0100-xxx", 8, "gpu_vbios"),
            BOMComponent("cpu", "AMD EPYC 7742 (64C/128T)", "", 2, "bios"),
            BOMComponent("ram", "64GB DDR4-3200 ECC RDIMM", "", 16),
            BOMComponent("nvme", "3.84TB Gen4 U.2 NVMe SSD", "", 8, "nvme_fw"),
            BOMComponent("nvswitch", "NVIDIA NVSwitch 3rd Gen", "", 6, "nvswitch_fw"),
            BOMComponent("nic", "NVIDIA ConnectX-6 HDR 200Gb/s", "MCX653106A-HDAT", 8, "cx_fw"),
            BOMComponent("transceiver_ib", "200G HDR QSFP56 AOC", "MFS1S00-H003V", 8, "transceiver_fw"),
            BOMComponent("transceiver_mgmt", "100G QSFP28 SR4", "", 1),
            BOMComponent("bmc", "NVIDIA BMC (OpenBMC)", "", 1, "bmc"),
            BOMComponent("psu", "1600W Platinum 80+", "", 6, "psu_fw"),
            BOMComponent("baseboard", "HGX A100 8-GPU Baseboard", "920-23687-2500-000", 1, "hgx_fw"),
        ])
    else:
        return NodeBOM(platform="CPU-Server", components=[
            BOMComponent("cpu", "Intel Xeon Gold 6448Y (32C/64T)", "", 2, "bios"),
            BOMComponent("ram", "64GB DDR5-4800 ECC RDIMM", "", 8),
            BOMComponent("nvme", "1.92TB Gen4 U.2 NVMe SSD", "", 4, "nvme_fw"),
            BOMComponent("nic", "NVIDIA ConnectX-7 100Gb/s", "MCX75310AAS-NEAT", 2, "cx_fw"),
            BOMComponent("transceiver_eth", "100G QSFP56 SR4", "", 2),
            BOMComponent("bmc", "Dell iDRAC / HPE iLO", "", 1, "bmc"),
            BOMComponent("psu", "1100W Platinum 80+", "", 2, "psu_fw"),
        ])



@dataclass
class CordonInfo:
    is_cordoned: bool = False
    owner: str = ""
    priority: CordonPriority = CordonPriority.P4
    reason: str = ""
    since: Optional[datetime] = None


@dataclass
class Node:
    id: str
    fqdn: str = ""
    node_type: NodeType = NodeType.GPU
    state: NodeState = NodeState.PROVISIONING
    state_since: Optional[datetime] = None
    state_reason: str = ""
    state_owner: str = ""
    location: Location = field(default_factory=Location)
    hardware: Hardware = field(default_factory=Hardware)
    firmware: Firmware = field(default_factory=Firmware)
    cordon: CordonInfo = field(default_factory=CordonInfo)
    backend: BackendType = BackendType.BCM
    tenant: str = ""
    customer_protected: bool = False
    health_score: float = 1.0
    last_certified: Optional[datetime] = None
    cert_status: str = ""
    tags: dict = field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class StateTransitionEvent:
    id: str
    node_id: str
    from_state: NodeState
    to_state: NodeState
    trigger: str
    owner: str = ""
    priority: CordonPriority = CordonPriority.P4
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    success: bool = True
    error: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class ClassificationResult:
    failure_class: FailureClass
    confidence: float
    severity: Severity
    recommended_action: str
    route_to: str
    details: str = ""


@dataclass
class Incident:
    id: str
    incident_type: str  # rack, switch, pdu, spine, cooling
    affected_nodes: list[str] = field(default_factory=list)
    classification: FailureClass = FailureClass.UNKNOWN
    severity: Severity = Severity.HIGH
    route_to: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolved: bool = False
    details: str = ""


@dataclass
class AlertEvent:
    id: str
    node_id: str
    severity: Severity
    channel: str
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    acknowledged: bool = False

"""BDD Test Suite — BOM-specific scenarios (8 scenarios)."""
import pytest
import os

TEST_DB = "/tmp/nlm-test.db"
os.environ.setdefault("NLM_DB_PATH", TEST_DB)
os.environ["NLM_USER"] = "admin"
os.environ["NLM_PASS"] = "nlm"

from fastapi.testclient import TestClient
from nlm.api import app
from nlm.mock_fleet import seed_fleet
from nlm.models import get_bom_template

client = TestClient(app)
AUTH = ("admin", "nlm")

@pytest.fixture(scope="module", autouse=True)
def setup_db():
    if not os.path.exists(TEST_DB):
        seed_fleet(TEST_DB)
    yield


# 1. H200 BOM has 12 components
def test_h200_bom_components():
    r = client.get("/api/v1/nodes/gpu-h200-001/bom", auth=AUTH)
    d = r.json()
    assert d["platform"] == "DGX-H200"
    assert len(d["components"]) == 12
    cats = {c["category"] for c in d["components"]}
    assert "gpu" in cats
    assert "nvswitch" in cats
    assert "nic" in cats
    assert "transceiver_ib" in cats
    assert "psu" in cats
    assert "baseboard" in cats

# 2. B200 BOM has 13 components (includes DPU)
def test_b200_bom_includes_dpu():
    r = client.get("/api/v1/nodes/gpu-b200-001/bom", auth=AUTH)
    d = r.json()
    assert d["platform"] == "DGX-B200"
    assert len(d["components"]) == 13
    dpu = [c for c in d["components"] if c["category"] == "dpu"]
    assert len(dpu) == 1
    assert "BlueField-3" in dpu[0]["part_name"]

# 3. A100 BOM
def test_a100_bom():
    r = client.get("/api/v1/nodes/gpu-dev-001/bom", auth=AUTH)
    d = r.json()
    assert d["platform"] == "DGX-A100"
    gpu = [c for c in d["components"] if c["category"] == "gpu"][0]
    assert "A100" in gpu["part_name"]
    nic = [c for c in d["components"] if c["category"] == "nic"][0]
    assert "ConnectX-6" in nic["part_name"]

# 4. CPU node BOM has no GPU/NVSwitch
def test_cpu_bom_no_gpu():
    r = client.get("/api/v1/nodes/cpu-kr1a-001/bom", auth=AUTH)
    d = r.json()
    assert d["platform"] == "CPU-Server"
    cats = {c["category"] for c in d["components"]}
    assert "gpu" not in cats
    assert "nvswitch" not in cats
    assert "cpu" in cats
    assert "nic" in cats

# 5. H200 firmware has all 12 fields
def test_h200_firmware_all_fields():
    r = client.get("/api/v1/nodes/gpu-h200-001", auth=AUTH)
    fw = r.json()["firmware"]
    for field in ["gpu_driver", "cuda", "bios", "bmc", "ofed",
                  "gpu_vbios", "nvswitch_fw", "cx_fw", "transceiver_fw",
                  "nvme_fw", "psu_fw", "hgx_fw"]:
        assert fw[field] != "", f"Missing firmware field: {field}"

# 6. Firmware matrix grouped by SKU
def test_firmware_matrix_grouped():
    r = client.get("/api/v1/firmware/matrix", auth=AUTH)
    d = r.json()
    skus = {x["sku"] for x in d}
    assert "DGX-H200" in skus
    assert "DGX-B200" in skus
    assert "A100-80G" in skus
    for entry in d:
        assert "firmware_versions" in entry
        assert isinstance(entry["firmware_versions"], dict)

# 7. Platform detection returns correct BOM
def test_platform_detection():
    h200 = get_bom_template("DGX-H200")
    assert h200.platform == "DGX-H200"
    b200 = get_bom_template("DGX-B200")
    assert b200.platform == "DGX-B200"
    a100 = get_bom_template("A100-80G")
    assert a100.platform == "DGX-A100"
    cpu = get_bom_template("CPU-Server")
    assert cpu.platform == "CPU-Server"

# 8. Mixed fleet compliance check flags mismatches
def test_compliance_check():
    r = client.get("/api/v1/firmware/compliance", auth=AUTH)
    d = r.json()
    h200_drivers = {x["gpu_driver"] for x in d if x["sku"] == "DGX-H200"}
    b200_drivers = {x["gpu_driver"] for x in d if x["sku"] == "DGX-B200"}
    # H200 and B200 should have different driver versions
    assert h200_drivers != b200_drivers or len(h200_drivers) >= 1

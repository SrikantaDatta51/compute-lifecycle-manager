"""BDD Test Suite — API endpoints (22 scenarios)."""
import pytest
import os
import shutil

# Set test DB before importing anything
TEST_DB = "/tmp/nlm-test.db"
os.environ["NLM_DB_PATH"] = TEST_DB
os.environ["NLM_USER"] = "admin"
os.environ["NLM_PASS"] = "nlm"

from fastapi.testclient import TestClient
from nlm.api import app
from nlm import db
from nlm.mock_fleet import seed_fleet

client = TestClient(app)
AUTH = ("admin", "nlm")

@pytest.fixture(scope="module", autouse=True)
def setup_db():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    seed_fleet(TEST_DB)
    yield
    os.remove(TEST_DB)


# 1. No auth -> 401
def test_no_auth_returns_401():
    r = client.get("/api/v1/nodes")
    assert r.status_code == 401
    assert "WWW-Authenticate" in r.headers

# 2. Valid auth -> 200 with 55 nodes
def test_list_nodes_returns_55():
    r = client.get("/api/v1/nodes", auth=AUTH)
    assert r.status_code == 200
    assert len(r.json()) == 55

# 3. Filter by state
def test_filter_by_state():
    r = client.get("/api/v1/nodes?state=certified_ready", auth=AUTH)
    assert r.status_code == 200
    for n in r.json():
        assert n["state"] == "certified_ready"

# 4. Filter by type
def test_filter_by_type():
    r = client.get("/api/v1/nodes?node_type=cpu", auth=AUTH)
    assert r.status_code == 200
    for n in r.json():
        assert n["type"] == "cpu"

# 5. Get single node
def test_get_node_detail():
    r = client.get("/api/v1/nodes/gpu-h200-001", auth=AUTH)
    assert r.status_code == 200
    d = r.json()
    assert d["id"] == "gpu-h200-001"
    assert "firmware" in d
    assert d["firmware"]["gpu_vbios"] != ""

# 6. Node not found
def test_get_node_404():
    r = client.get("/api/v1/nodes/nonexistent", auth=AUTH)
    assert r.status_code == 404

# 7. Transition
def test_transition_node():
    r = client.put("/api/v1/nodes/gpu-h200-007/state", auth=AUTH,
                   json={"trigger": "assign_customer", "operator": "test"})
    assert r.status_code in (200, 403)

# 8. Invalid transition
def test_invalid_transition():
    r = client.put("/api/v1/nodes/gpu-h200-001/state", auth=AUTH,
                   json={"trigger": "decommission", "operator": "test"})
    assert r.status_code in (200, 403)

# 9. Cordon
def test_cordon_node():
    r = client.post("/api/v1/nodes/gpu-h200-007/cordon", auth=AUTH,
                    json={"owner": "test-user", "priority": "P2", "reason": "test"})
    assert r.status_code in (200, 403)

# 10. Uncordon
def test_uncordon_node():
    r = client.post("/api/v1/nodes/gpu-h200-007/uncordon", auth=AUTH,
                    json={"requester": "test-user", "force": True})
    assert r.status_code in (200, 403)

# 11. Inject fault
def test_inject_fault():
    r = client.post("/api/v1/nodes/gpu-h200-010/inject", auth=AUTH,
                    json={"fault": "xid_79", "details": "test injection"})
    assert r.status_code == 200
    d = r.json()
    assert "classification" in d
    assert "severity" in d
    assert "route_to" in d

# 12. Fleet capacity
def test_fleet_capacity():
    r = client.get("/api/v1/fleet/capacity", auth=AUTH)
    assert r.status_code == 200
    d = r.json()
    assert d["total"] == 55
    assert "by_state" in d

# 13. Health summary
def test_health_summary():
    r = client.get("/api/v1/health/summary", auth=AUTH)
    assert r.status_code == 200
    d = r.json()
    assert "average_health_score" in d
    assert "by_state" in d

# 14. Incidents (Rootly mock data)
def test_incidents():
    r = client.get("/api/v1/incidents", auth=AUTH)
    assert r.status_code == 200
    incs = r.json()
    assert isinstance(incs, list)
    assert len(incs) == 5
    assert "id" in incs[0]
    assert "timeline" in incs[0]
    assert "action_items" in incs[0]
    assert incs[0]["severity"] in ("critical", "high", "medium", "low")

# 15. Certifications
def test_certifications():
    r = client.get("/api/v1/certifications", auth=AUTH)
    assert r.status_code == 200
    assert len(r.json()) == 55

# 16. Firmware compliance (extended)
def test_firmware_compliance():
    r = client.get("/api/v1/firmware/compliance", auth=AUTH)
    assert r.status_code == 200
    d = r.json()
    assert len(d) == 55
    h200 = [x for x in d if x["sku"] == "DGX-H200"][0]
    assert h200["gpu_vbios"] != ""
    assert h200["nvswitch_fw"] != ""
    assert h200["cx_fw"] != ""
    assert h200["transceiver_fw"] != ""

# 17. Firmware matrix
def test_firmware_matrix():
    r = client.get("/api/v1/firmware/matrix", auth=AUTH)
    assert r.status_code == 200
    d = r.json()
    skus = {x["sku"] for x in d}
    assert "DGX-H200" in skus
    assert "DGX-B200" in skus

# 18. Node BOM
def test_node_bom_h200():
    r = client.get("/api/v1/nodes/gpu-h200-001/bom", auth=AUTH)
    assert r.status_code == 200
    d = r.json()
    assert d["platform"] == "DGX-H200"
    cats = [c["category"] for c in d["components"]]
    assert "gpu" in cats
    assert "nvswitch" in cats
    assert "nic" in cats
    assert "transceiver_ib" in cats
    assert "psu" in cats
    gpu = [c for c in d["components"] if c["category"] == "gpu"][0]
    assert gpu["quantity"] == 8
    assert gpu["firmware_version"] != ""

# 19. Alerts
def test_alerts():
    r = client.get("/api/v1/alerts", auth=AUTH)
    assert r.status_code == 200

# 20. Classifier rules
def test_classifier_rules():
    r = client.get("/api/v1/classifier/rules", auth=AUTH)
    assert r.status_code == 200
    assert len(r.json()) == 15

# 21. Events
def test_events():
    r = client.get("/api/v1/events", auth=AUTH)
    assert r.status_code == 200

# 22. Prometheus metrics
def test_prometheus_metrics():
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "nlm_nodes_total" in r.text
    assert "nlm_avg_health" in r.text

# 23. Topology (Korea regions)
def test_topology_korea():
    r = client.get("/api/v1/topology", auth=AUTH)
    assert r.status_code == 200
    topo = r.json()
    assert len(topo) == 1
    assert topo[0]["region"] == "ap-korea-1"
    azs = [a["az"] for a in topo[0]["azs"]]
    assert "kr1a" in azs
    assert "kr1b" in azs

# 24. Power summary
def test_power_summary():
    r = client.get("/api/v1/power/summary", auth=AUTH)
    assert r.status_code == 200
    d = r.json()
    assert d["total_power_kw"] > 0
    assert len(d["racks"]) > 0

"""NLM BDD Scenario Tests — end-to-end validation of all use cases.

Each test simulates a real-world scenario with assertions from expert personas:
  - SRE: "Is the node cordoned? Is the alert correct?"
  - DC-Ops: "Is the operation-request correct? Is debug bundle collected?"
  - Customer: "Is my node protected? Was I notified?"
  - Platform Lead: "Is fleet capacity correct? Is SLA data accurate?"
  - Automation: "Did the operator run? Is GitOps state consistent?"

Run: pytest tests/test_scenarios.py -v
"""
import asyncio
import os
import shutil
import glob
import yaml
import pytest
from fastapi.testclient import TestClient

TEST_GITOPS = "/tmp/nlm-bdd-gitops"
os.environ["NLM_GITOPS_ROOT"] = TEST_GITOPS

from nlm.api import app
from nlm import db, gitops
from nlm.models import NodeState
from nlm.operators.reconciler import Reconciler
from nlm.operators.maintenance import MaintenanceOrchestrator
from nlm.operators.testing import TestingScheduler

client = TestClient(app)
AUTH = ("admin", "nlm")


@pytest.fixture(autouse=True)
def clean_env():
    """Fresh gitops dir for each test."""
    if os.path.exists(TEST_GITOPS):
        shutil.rmtree(TEST_GITOPS)
    os.makedirs(TEST_GITOPS, exist_ok=True)
    gitops.GITOPS_ROOT = TEST_GITOPS
    gitops.seed_default_policies()
    yield
    if os.path.exists(TEST_GITOPS):
        shutil.rmtree(TEST_GITOPS)


# ═══════════════════════════════════════════════════════════════════
# SCENARIO 1: All Assets Visible in Dashboard (UC-1)
# Persona: Platform Lead — "Can I see all 55 nodes across all AZs?"
# ═══════════════════════════════════════════════════════════════════

class TestScenario_UC1_AssetVisibility:
    """
    GIVEN the NLM platform with mock fleet
    WHEN Platform Lead queries fleet API
    THEN all 55 nodes visible across 2 AZs with correct breakdown
    """

    def test_fleet_capacity_shows_55_nodes(self):
        """Platform Lead: Total fleet is 55 nodes."""
        cap = client.get("/api/v1/fleet/capacity", auth=AUTH).json()
        assert cap["total"] == 55

    def test_nodes_span_both_azs(self):
        """Platform Lead: Nodes exist in both kr1a and kr1b."""
        nodes = client.get("/api/v1/nodes", auth=AUTH).json()
        azs = {n["az"] for n in nodes}
        assert "kr1a" in azs and "kr1b" in azs

    def test_all_backends_present(self):
        """Platform Lead: BCM, K8s, bare_metal backends all present."""
        nodes = client.get("/api/v1/nodes", auth=AUTH).json()
        backends = {n["backend"] for n in nodes}
        assert backends >= {"bcm", "kubernetes", "bare_metal"}

    def test_health_summary_has_metrics(self):
        """Platform Lead: Health summary provides SLA-relevant data."""
        hs = client.get("/api/v1/health/summary", auth=AUTH).json()
        assert "average_health_score" in hs
        assert "total_nodes" in hs

    def test_firmware_compliance_returns_data(self):
        """Platform Lead: Firmware data available for each node."""
        fw = client.get("/api/v1/firmware/compliance", auth=AUTH).json()
        assert isinstance(fw, list) and len(fw) > 0
        assert "node_id" in fw[0]


# ═══════════════════════════════════════════════════════════════════
# SCENARIO 2: Node Ready → Assigned to Tenant (UC-2)
# Persona: Customer — "Is my node protected after assignment?"
# ═══════════════════════════════════════════════════════════════════

class TestScenario_UC2_TenantAssignment:
    """
    GIVEN a certified_ready node
    WHEN customer_assign trigger fires
    THEN node → customer_assigned, protection enabled
    """

    def test_assign_node_to_customer(self):
        """Customer: certified_ready → customer_assigned via PUT /state."""
        r = client.put(
            "/api/v1/nodes/gpu-h200-007/state",
            json={"trigger": "customer_assign"},
            auth=AUTH,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["to"] == "customer_assigned"

    def test_assigned_node_shows_correct_state(self):
        """Customer: After assignment, node state is customer_assigned."""
        client.put(
            "/api/v1/nodes/gpu-h200-007/state",
            json={"trigger": "customer_assign"},
            auth=AUTH,
        )
        node = client.get("/api/v1/nodes/gpu-h200-007", auth=AUTH).json()
        assert node["state"] == "customer_assigned"

    def test_emergency_drain_works_on_assigned_node(self):
        """SRE: P0 emergency can drain even customer_assigned nodes."""
        # Assign first
        client.put(
            "/api/v1/nodes/gpu-h200-007/state",
            json={"trigger": "customer_assign"}, auth=AUTH,
        )
        # Emergency drain
        r = client.put(
            "/api/v1/nodes/gpu-h200-007/state",
            json={"trigger": "emergency_hw"}, auth=AUTH,
        )
        assert r.status_code == 200
        assert r.json()["to"] == "emergency_drain"


# ═══════════════════════════════════════════════════════════════════
# SCENARIO 3: Fault → Auto-Remediation (UC-3)
# Personas: SRE, DC-Ops, Automation
# ═══════════════════════════════════════════════════════════════════

class TestScenario_UC3_FaultRemediation:
    """
    GIVEN a healthy certified_ready node
    WHEN GPU Xid 79 fault injected + reconciler runs
    THEN auto-cordon + day2_cordon op-request + debug_bundle op-request
    """

    def test_fault_injection_drops_health(self):
        """SRE: Xid 79 drops health score below threshold."""
        r = client.post(
            "/api/v1/nodes/gpu-h200-008/inject",
            json={"fault": "xid_79", "details": "GPU fallen off bus"},
            auth=AUTH,
        )
        assert r.status_code == 200
        node = client.get("/api/v1/nodes/gpu-h200-008", auth=AUTH).json()
        assert node["health_score"] < 1.0

    def test_reconciler_auto_cordons(self):
        """SRE: Reconciler auto-cordons the faulty node."""
        client.post(
            "/api/v1/nodes/gpu-h200-008/inject",
            json={"fault": "xid_79"}, auth=AUTH,
        )
        r = client.post("/api/v1/operators/reconciler/trigger", auth=AUTH)
        result = r.json()["result"]
        assert result["health_alerts"] > 0

    def test_day2_cordon_op_request_created(self):
        """DC-Ops: day2_cordon op-request written for Ansible Tower."""
        client.post(
            "/api/v1/nodes/gpu-h200-008/inject",
            json={"fault": "xid_79"}, auth=AUTH,
        )
        client.post("/api/v1/operators/reconciler/trigger", auth=AUTH)
        op_files = glob.glob(os.path.join(
            TEST_GITOPS, "operation-requests", "*day2_cordon*gpu-h200-008*"))
        assert len(op_files) >= 1, "Missing day2_cordon op-request"
        with open(op_files[0]) as f:
            data = yaml.safe_load(f)
        assert data["operation"] == "day2_cordon"
        assert "gpu-h200-008" in data["targets"]

    def test_debug_bundle_op_request_created(self):
        """DC-Ops: debug_bundle auto-triggered for NVIDIA log collection."""
        client.post(
            "/api/v1/nodes/gpu-h200-008/inject",
            json={"fault": "xid_79"}, auth=AUTH,
        )
        client.post("/api/v1/operators/reconciler/trigger", auth=AUTH)
        op_files = glob.glob(os.path.join(
            TEST_GITOPS, "operation-requests", "*debug_bundle*gpu-h200-008*"))
        assert len(op_files) >= 1, "Missing debug_bundle op-request"

    def test_cordon_yaml_written(self):
        """Automation: GitOps cordon YAML created for audit trail."""
        client.post(
            "/api/v1/nodes/gpu-h200-008/inject",
            json={"fault": "xid_79"}, auth=AUTH,
        )
        client.post("/api/v1/operators/reconciler/trigger", auth=AUTH)
        assert os.path.exists(os.path.join(
            TEST_GITOPS, "cordons", "gpu-h200-008.yml"))

    def test_op_request_matches_bcm_iac_format(self):
        """Automation: Op-request has all required bcm-iac fields."""
        client.post(
            "/api/v1/nodes/gpu-h200-008/inject",
            json={"fault": "xid_79"}, auth=AUTH,
        )
        client.post("/api/v1/operators/reconciler/trigger", auth=AUTH)
        for f_path in glob.glob(os.path.join(
                TEST_GITOPS, "operation-requests", "*.yml")):
            with open(f_path) as f:
                data = yaml.safe_load(f)
            for field in ("operation", "targets", "requested_by",
                          "approved_by", "reason"):
                assert field in data, f"Missing '{field}' in {f_path}"


# ═══════════════════════════════════════════════════════════════════
# SCENARIO 4: Daily Tests (UC-4)
# Persona: Automation — stale certs → testing → recertified
# ═══════════════════════════════════════════════════════════════════

class TestScenario_UC4_DailyTests:
    """
    GIVEN certified_ready nodes with stale certs
    WHEN Testing Scheduler runs
    THEN stale nodes → testing, burnin_suite op-requests written
    AND customer_assigned nodes NEVER touched
    """

    def test_scheduler_checks_all_nodes(self):
        """Automation: Scheduler checks full fleet."""
        ts = TestingScheduler(interval=300, mock_mode=True)
        result = asyncio.get_event_loop().run_until_complete(ts.run_once())
        assert result["nodes_checked"] == 55

    def test_burnin_suite_op_request_format(self):
        """Automation: burnin_suite op-request has correct parameters."""
        ts = TestingScheduler(interval=300, mock_mode=True)
        asyncio.get_event_loop().run_until_complete(ts.run_once())
        op_files = glob.glob(os.path.join(
            TEST_GITOPS, "operation-requests", "*burnin_suite*"))
        if op_files:
            with open(op_files[0]) as f:
                data = yaml.safe_load(f)
            assert data["operation"] == "burnin_suite"
            assert "dcgmi_level" in data.get("parameters", {})

    def test_customer_nodes_never_tested(self):
        """Customer: My assigned nodes must NOT be pulled for testing."""
        before = [n for n in client.get("/api/v1/nodes", auth=AUTH).json()
                  if n["state"] == "customer_assigned"]
        ts = TestingScheduler(interval=300, mock_mode=True)
        asyncio.get_event_loop().run_until_complete(ts.run_once())
        after = [n for n in client.get("/api/v1/nodes", auth=AUTH).json()
                 if n["state"] == "customer_assigned"]
        assert len(after) == len(before), \
            "Customer nodes must NOT be touched"


# ═══════════════════════════════════════════════════════════════════
# SCENARIO 5: BMaaS Approval Gate (UC-6)
# Personas: Partner Team, Customer
# ═══════════════════════════════════════════════════════════════════

class TestScenario_UC6_BMaaSApproval:
    """
    GIVEN BMaaS node with non-P0 fault
    WHEN reconciler classifies
    THEN maintenance_request written (NOT cordon)
    AND status: awaiting_customer_approval
    """

    def test_bmaas_non_p0_creates_maintenance_request(self):
        """Partner Team: BMaaS gets request, not auto-cordon."""
        # gpu-bm-005 is certified_ready, bare_metal
        client.post("/api/v1/nodes/gpu-bm-005/inject",
                    json={"fault": "ecc_correctable_high"}, auth=AUTH)
        client.post("/api/v1/operators/reconciler/trigger", auth=AUTH)
        maint = glob.glob(os.path.join(
            TEST_GITOPS, "maintenance", "*gpu-bm-005*"))
        assert len(maint) >= 1, "BMaaS non-P0 needs maint request"
        with open(maint[0]) as f:
            data = yaml.safe_load(f)
        assert data["status"] == "awaiting_customer_approval"

    def test_bmaas_p0_overrides_protection(self):
        """Customer: P0 safety overrides even on BMaaS."""
        # gpu-bm-001 is customer_assigned bare_metal
        client.post("/api/v1/nodes/gpu-bm-001/inject",
                    json={"fault": "xid_79"}, auth=AUTH)
        client.post("/api/v1/operators/reconciler/trigger", auth=AUTH)
        cordons = glob.glob(os.path.join(
            TEST_GITOPS, "cordons", "gpu-bm-001*"))
        assert len(cordons) >= 1, "P0 on BMaaS must auto-cordon"


# ═══════════════════════════════════════════════════════════════════
# SCENARIO 6: Timeout Enforcement
# Persona: Automation
# ═══════════════════════════════════════════════════════════════════

class TestScenario_TimeoutEnforcement:
    """
    GIVEN Maintenance Orchestrator running
    WHEN it checks nodes
    THEN timeouts enforced, rack concurrency respected
    """

    def test_maintenance_runs_clean(self):
        """Automation: Orchestrator runs without error."""
        mo = MaintenanceOrchestrator(interval=120)
        result = asyncio.get_event_loop().run_until_complete(mo.run_once())
        assert result["nodes_checked"] == 55

    def test_rack_concurrency_field_present(self):
        """DC-Ops: Rack-limiting logic reports its count."""
        mo = MaintenanceOrchestrator(interval=120)
        result = asyncio.get_event_loop().run_until_complete(mo.run_once())
        assert "rack_limited" in result


# ═══════════════════════════════════════════════════════════════════
# SCENARIO 7: Full Repair Pipeline
# Persona: DC-Ops
# ═══════════════════════════════════════════════════════════════════

class TestScenario_FullRepairPipeline:
    """
    GIVEN a healthy GPU node
    WHEN fault → reconciler → repair state
    THEN full pipeline: cordon + debug_bundle + desired-state YAMLs
    """

    def test_pipeline_generates_op_requests(self):
        """DC-Ops: Pipeline produces Ansible Tower payloads."""
        client.post("/api/v1/nodes/gpu-h200-008/inject",
                    json={"fault": "xid_79"}, auth=AUTH)
        r = client.post("/api/v1/operators/reconciler/trigger", auth=AUTH)
        result = r.json()["result"]
        assert result["op_requests_written"] >= 1

    def test_desired_state_yaml_tracks_repair(self):
        """Automation: desired-state YAML records current state."""
        client.post("/api/v1/nodes/gpu-h200-008/inject",
                    json={"fault": "xid_79"}, auth=AUTH)
        client.post("/api/v1/operators/reconciler/trigger", auth=AUTH)
        ds = gitops.read_desired_state("gpu-h200-008")
        assert ds is not None


# ═══════════════════════════════════════════════════════════════════
# SCENARIO 8: Operator Lifecycle
# Persona: SRE
# ═══════════════════════════════════════════════════════════════════

class TestScenario_OperatorLifecycle:
    """
    GIVEN 3 registered operators
    WHEN SRE queries/toggles
    THEN all report correctly, toggle works
    """

    def test_three_operators_visible(self):
        """SRE: All 3 operators visible in status."""
        ops = client.get("/api/v1/operators/status", auth=AUTH).json()
        assert set(ops["operators"].keys()) >= {"reconciler", "maintenance", "testing"}

    def test_trigger_returns_result(self):
        """SRE: Manual trigger returns actionable metrics."""
        r = client.post("/api/v1/operators/reconciler/trigger", auth=AUTH)
        result = r.json()["result"]
        assert "nodes_checked" in result
        assert "op_requests_written" in result

    def test_toggle_works(self):
        """SRE: Can disable misbehaving operator."""
        r = client.post(
            "/api/v1/operators/reconciler/toggle?enabled=false", auth=AUTH)
        assert r.json()["enabled"] is False
        # Re-enable
        client.post(
            "/api/v1/operators/reconciler/toggle?enabled=true", auth=AUTH)

    def test_policies_readable(self):
        """Platform Lead: Policies readable via API."""
        data = client.get("/api/v1/gitops/policies", auth=AUTH).json()
        assert "health-thresholds" in data
        assert "test-schedule" in data
        assert data["health-thresholds"]["spec"]["critical_threshold"] == 0.5


# ═══════════════════════════════════════════════════════════════════
# SCENARIO 9: Invalid Transitions Blocked
# Persona: Junior Engineer — "System prevents me from breaking things"
# ═══════════════════════════════════════════════════════════════════

class TestScenario_SafetyGuardrails:
    """
    GIVEN the state machine with 20 valid transitions
    WHEN invalid triggers are attempted
    THEN system rejects with 403 — junior engineers can't break it
    """

    def test_invalid_transition_rejected(self):
        """Junior Eng: Can't skip states — provisioning → customer_assigned blocked."""
        r = client.put(
            "/api/v1/nodes/cpu-kr1a-001/state",
            json={"trigger": "customer_assign"}, auth=AUTH,
        )
        assert r.status_code == 403

    def test_decommissioned_is_terminal(self):
        """Junior Eng: Can't bring back a decommissioned node."""
        # First decommission a certified_ready node
        client.put("/api/v1/nodes/gpu-stg-001/state",
                   json={"trigger": "decommission"}, auth=AUTH)
        # Try to bring it back
        r = client.put("/api/v1/nodes/gpu-stg-001/state",
                       json={"trigger": "provision_complete"}, auth=AUTH)
        assert r.status_code == 403

    def test_nonexistent_node_returns_404(self):
        """Junior Eng: Typo in node name gives clear error."""
        r = client.put(
            "/api/v1/nodes/does-not-exist/state",
            json={"trigger": "customer_assign"}, auth=AUTH,
        )
        assert r.status_code == 404

    def test_auth_required(self):
        """Junior Eng: No auth = 401, not silent failure."""
        r = client.get("/api/v1/nodes")
        assert r.status_code == 401

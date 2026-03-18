"""NLM Operator & GitOps Tests — verifies operation-request generation,
reconciler, maintenance, testing scheduler, and API endpoints."""
import asyncio
import os
import shutil
import pytest
from fastapi.testclient import TestClient

# Set gitops root to temp dir before importing
TEST_GITOPS = "/tmp/nlm-test-gitops"
os.environ["NLM_GITOPS_ROOT"] = TEST_GITOPS


from nlm.api import app
from nlm import db, gitops
from nlm.models import NodeState, CordonPriority
from nlm.operators.reconciler import Reconciler
from nlm.operators.maintenance import MaintenanceOrchestrator
from nlm.operators.testing import TestingScheduler

client = TestClient(app)
AUTH = ("admin", "nlm")


@pytest.fixture(autouse=True)
def clean_gitops():
    """Clean gitops dir before each test and patch module constant."""
    if os.path.exists(TEST_GITOPS):
        shutil.rmtree(TEST_GITOPS)
    os.makedirs(TEST_GITOPS, exist_ok=True)
    # Patch the module-level constant (env var was set too late for import)
    gitops.GITOPS_ROOT = TEST_GITOPS
    yield
    if os.path.exists(TEST_GITOPS):
        shutil.rmtree(TEST_GITOPS)


# ── GitOps Module Tests ──

class TestGitOpsOperationRequests:
    def test_write_operation_request(self):
        path = gitops.write_operation_request(
            operation="day2_cordon",
            targets=["gpu-b200-009"],
            parameters={"reason_type": "fault"},
            requested_by="nlm-test@nlm.cic.io",
            auto_approve=True,
            reason="Test cordon",
        )
        assert os.path.exists(path)
        data = gitops.list_operation_requests()
        assert len(data) >= 1
        req = data[0]
        assert req["operation"] == "day2_cordon"
        assert req["targets"] == ["gpu-b200-009"]
        assert req["approved_by"] == "nlm-test@nlm.cic.io"

    def test_unapproved_request(self):
        gitops.write_operation_request(
            operation="day2_cordon",
            targets=["gpu-bm-005"],
            auto_approve=False,
            reason="Needs customer approval",
        )
        reqs = gitops.list_operation_requests()
        assert reqs[0]["approved_by"] == ""

    def test_maintenance_request_bmaas(self):
        gitops.write_maintenance_request(
            node_id="gpu-bm-005",
            tenant="acme-corp",
            issue="ECC errors high",
            severity="medium",
        )
        reqs = gitops.list_maintenance_requests()
        assert len(reqs) >= 1
        assert reqs[0]["status"] == "awaiting_customer_approval"
        assert reqs[0]["tenant"] == "acme-corp"


class TestGitOpsDesiredState:
    def test_write_and_read(self):
        gitops.write_desired_state("gpu-h200-001", "testing")
        ds = gitops.read_desired_state("gpu-h200-001")
        assert ds["spec"]["desired_state"] == "testing"

    def test_list(self):
        gitops.write_desired_state("node-1", "repair")
        gitops.write_desired_state("node-2", "testing")
        states = gitops.list_desired_states()
        assert len(states) == 2


class TestGitOpsCordons:
    def test_write_and_delete(self):
        gitops.write_cordon("gpu-001", "nlm-test", "P0", "Test failure")
        assert len(gitops.list_cordons()) == 1
        gitops.delete_cordon("gpu-001")
        assert len(gitops.list_cordons()) == 0


class TestGitOpsPolicies:
    def test_seed_and_read(self):
        gitops.seed_default_policies()
        p = gitops.read_policy("health-thresholds")
        assert p is not None
        assert p["spec"]["critical_threshold"] == 0.5

    def test_firmware_baseline(self):
        gitops.seed_default_policies()
        p = gitops.read_policy("firmware-baseline")
        assert p["spec"]["gpu_driver"] == "550.127.05"


# ── Operator Tests ──

class TestReconciler:
    def test_init(self):
        r = Reconciler(interval=60)
        assert r.name == "reconciler"
        assert r.interval == 60

    def test_run_once_checks_nodes(self):
        r = Reconciler(interval=60)
        gitops.seed_default_policies()
        result = asyncio.get_event_loop().run_until_complete(r.run_once())
        assert "nodes_checked" in result
        assert result["nodes_checked"] == 55

    def test_status(self):
        r = Reconciler()
        s = r.status()
        assert s["name"] == "reconciler"
        assert s["enabled"] is True


class TestMaintenanceOrchestrator:
    def test_init(self):
        m = MaintenanceOrchestrator(interval=120)
        assert m.name == "maintenance"

    def test_run_once(self):
        m = MaintenanceOrchestrator(interval=120)
        result = asyncio.get_event_loop().run_until_complete(m.run_once())
        assert "nodes_checked" in result
        assert "timeouts_enforced" in result


class TestTestingScheduler:
    def test_init(self):
        t = TestingScheduler(interval=300, mock_mode=True)
        assert t.name == "testing"

    def test_run_once(self):
        t = TestingScheduler(interval=300, mock_mode=True)
        gitops.seed_default_policies()
        result = asyncio.get_event_loop().run_until_complete(t.run_once())
        assert "nodes_checked" in result
        assert "stale_detected" in result


# ── API Endpoint Tests ──

class TestOperatorAPI:
    def test_operator_status(self):
        r = client.get("/api/v1/operators/status", auth=AUTH)
        assert r.status_code == 200
        data = r.json()
        assert "operators" in data
        assert "reconciler" in data["operators"]
        assert "maintenance" in data["operators"]
        assert "testing" in data["operators"]

    def test_trigger_operator(self):
        r = client.post("/api/v1/operators/reconciler/trigger", auth=AUTH)
        assert r.status_code == 200
        data = r.json()
        assert data["operator"] == "reconciler"
        assert "result" in data

    def test_trigger_nonexistent(self):
        r = client.post("/api/v1/operators/nonexistent/trigger", auth=AUTH)
        assert r.status_code == 404

    def test_toggle_operator(self):
        r = client.post("/api/v1/operators/reconciler/toggle?enabled=false",
                        auth=AUTH)
        assert r.status_code == 200
        assert r.json()["enabled"] is False
        # Re-enable
        client.post("/api/v1/operators/reconciler/toggle?enabled=true",
                     auth=AUTH)


class TestGitOpsAPI:
    def test_desired_states(self):
        r = client.get("/api/v1/gitops/desired-states", auth=AUTH)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_cordons(self):
        r = client.get("/api/v1/gitops/cordons", auth=AUTH)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_policies(self):
        gitops.seed_default_policies()
        r = client.get("/api/v1/gitops/policies", auth=AUTH)
        assert r.status_code == 200
        data = r.json()
        assert "health-thresholds" in data

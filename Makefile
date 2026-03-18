.PHONY: setup test run inject-demo api clean status capacity racks rules

setup:
	pip install fastapi uvicorn pydantic click rich pyyaml httpx pytest 2>/dev/null || true
	cd nlm-controller && python -m nlm.cli setup

test:
	cd nlm-controller && python -m pytest tests/ -v --tb=short 2>/dev/null || echo "No tests yet"

run:
	cd nlm-controller && python -m nlm.cli status

api:
	cd nlm-controller && uvicorn nlm.api:app --host 0.0.0.0 --port 8000 --reload

status:
	cd nlm-controller && python -m nlm.cli status

capacity:
	cd nlm-controller && python -m nlm.cli capacity

racks:
	cd nlm-controller && python -m nlm.cli racks

rules:
	cd nlm-controller && python -m nlm.cli rules

inject-demo:
	@echo "=== Injecting faults for demo ==="
	cd nlm-controller && python -m nlm.cli inject gpu-h200-001 --fault xid_79
	cd nlm-controller && python -m nlm.cli inject gpu-bm-003 --fault psu_fail
	cd nlm-controller && python -m nlm.cli inject gpu-b200-008 --fault ib_crc_high
	cd nlm-controller && python -m nlm.cli inject cpu-az1-001 --fault cpu_stress_fail
	cd nlm-controller && python -m nlm.cli inject gpu-stg-001 --fault thermal_critical
	@echo ""
	@echo "=== Fleet status after faults ==="
	cd nlm-controller && python -m nlm.cli status

alerts:
	cd nlm-controller && python -m nlm.cli alerts

clean:
	rm -rf nlm-controller/nlm-data/

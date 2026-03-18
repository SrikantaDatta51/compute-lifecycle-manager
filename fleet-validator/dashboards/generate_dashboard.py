#!/usr/bin/env python3
"""
Fleet Validation Framework — Grafana Dashboard Generator
=========================================================
Generates the "Continuous Monitoring and Fleet Validation Framework"
Grafana dashboard JSON. Designed for Prometheus data source.

Usage:
    python3 generate_dashboard.py [--output <path>]

Dashboard Rows:
    1. Fleet Overview       — Stat panels: total, certified, rate, last run
    2. Node State Map       — Pie chart + state timeline
    3. Certification Heatmap — Node × Test pass/fail matrix
    4. GPU Stress Metrics   — DCGMI, ECC, temperature
    5. NCCL Bandwidth       — Bus bandwidth per node vs threshold
    6. HPL Performance      — TFLOPS per node
    7. NVBandwidth          — H2D, D2D, bidirectional
    8. Alerts & History     — Active alerts, state change log
"""

import json
import sys
import os

OUTPUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "fleet-validation-dashboard.json")

if "--output" in sys.argv:
    idx = sys.argv.index("--output")
    OUTPUT_PATH = sys.argv[idx + 1]

# ─── Color Palette ───
COLORS = {
    "green":  "#22c55e",
    "red":    "#ef4444",
    "amber":  "#f59e0b",
    "blue":   "#3b82f6",
    "purple": "#8b5cf6",
    "cyan":   "#06b6d4",
    "slate":  "#64748b",
}


def make_panel(title, panel_type, grid_pos, targets, overrides=None,
               thresholds=None, options=None, field_config=None,
               description="", repeat=None):
    """Generate a Grafana panel."""
    panel = {
        "title": title,
        "type": panel_type,
        "gridPos": grid_pos,
        "datasource": {"type": "prometheus", "uid": "${DS_PROMETHEUS}"},
        "targets": targets,
        "description": description,
    }
    if options:
        panel["options"] = options
    if field_config:
        panel["fieldConfig"] = field_config
    if overrides:
        panel.setdefault("fieldConfig", {}).setdefault("overrides", []).extend(overrides)
    if thresholds:
        panel.setdefault("fieldConfig", {}).setdefault("defaults", {})["thresholds"] = thresholds
    if repeat:
        panel["repeat"] = repeat
        panel["repeatDirection"] = "h"
    return panel


def prom_target(expr, legend="", instant=False, ref_id="A"):
    """Generate a Prometheus target."""
    t = {
        "expr": expr,
        "legendFormat": legend,
        "refId": ref_id,
        "datasource": {"type": "prometheus", "uid": "${DS_PROMETHEUS}"},
    }
    if instant:
        t["instant"] = True
        t["range"] = False
    else:
        t["range"] = True
    return t


def stat_panel(title, expr, grid_pos, color=None, unit="", thresholds=None, desc=""):
    """Stat panel shorthand."""
    fc = {
        "defaults": {
            "unit": unit,
            "color": {"mode": "thresholds"},
            "thresholds": thresholds or {
                "mode": "absolute",
                "steps": [
                    {"color": COLORS["green"], "value": None},
                ]
            },
        }
    }
    if color:
        fc["defaults"]["color"] = {"fixedColor": color, "mode": "fixed"}

    return make_panel(
        title, "stat", grid_pos,
        [prom_target(expr, instant=True)],
        field_config=fc,
        description=desc,
    )


def generate_dashboard():
    """Build the complete dashboard."""
    panels = []
    panel_id = 1

    # ═══════════════════════════════════════════════════════════════
    # Row 1: Fleet Overview
    # ═══════════════════════════════════════════════════════════════
    panels.append({
        "type": "row",
        "title": "🏢 Fleet Overview",
        "gridPos": {"h": 1, "w": 24, "x": 0, "y": 0},
        "collapsed": False,
        "id": panel_id,
    })
    panel_id += 1

    # Total nodes
    p = stat_panel(
        "Total Nodes", 'count(fleet_cert_node_certified)',
        {"h": 4, "w": 4, "x": 0, "y": 1},
        color=COLORS["blue"], desc="Total nodes in fleet"
    )
    p["id"] = panel_id; panel_id += 1
    panels.append(p)

    # Certified nodes
    p = stat_panel(
        "Certified ✅", 'count(fleet_cert_node_certified == 1)',
        {"h": 4, "w": 4, "x": 4, "y": 1},
        thresholds={"mode": "absolute", "steps": [
            {"color": COLORS["red"], "value": None},
            {"color": COLORS["amber"], "value": 50},
            {"color": COLORS["green"], "value": 60},
        ]},
        desc="Nodes with valid certification"
    )
    p["id"] = panel_id; panel_id += 1
    panels.append(p)

    # Failed nodes
    p = stat_panel(
        "Failed ❌", 'count(fleet_cert_node_certified == 0)',
        {"h": 4, "w": 4, "x": 8, "y": 1},
        thresholds={"mode": "absolute", "steps": [
            {"color": COLORS["green"], "value": None},
            {"color": COLORS["amber"], "value": 1},
            {"color": COLORS["red"], "value": 3},
        ]},
        desc="Nodes that failed last certification"
    )
    p["id"] = panel_id; panel_id += 1
    panels.append(p)

    # Pass rate
    p = stat_panel(
        "Pass Rate", 'fleet_cert_pass_rate',
        {"h": 4, "w": 4, "x": 12, "y": 1},
        unit="percent",
        thresholds={"mode": "absolute", "steps": [
            {"color": COLORS["red"], "value": None},
            {"color": COLORS["amber"], "value": 80},
            {"color": COLORS["green"], "value": 95},
        ]},
        desc="Certification pass rate"
    )
    p["id"] = panel_id; panel_id += 1
    panels.append(p)

    # Last run
    p = stat_panel(
        "Last Run", 'fleet_cert_last_run_timestamp',
        {"h": 4, "w": 4, "x": 16, "y": 1},
        unit="dateTimeFromNow",
        desc="Time since last certification run"
    )
    p["id"] = panel_id; panel_id += 1
    panels.append(p)

    # Active alerts
    p = stat_panel(
        "Active Alerts 🔔", 'count(ALERTS{alertname=~"Fleet.*"}) or vector(0)',
        {"h": 4, "w": 4, "x": 20, "y": 1},
        thresholds={"mode": "absolute", "steps": [
            {"color": COLORS["green"], "value": None},
            {"color": COLORS["red"], "value": 1},
        ]},
        desc="Active fleet validation alerts"
    )
    p["id"] = panel_id; panel_id += 1
    panels.append(p)

    # ═══════════════════════════════════════════════════════════════
    # Row 2: Node State Distribution
    # ═══════════════════════════════════════════════════════════════
    panels.append({
        "type": "row",
        "title": "🗺️ Node State Distribution",
        "gridPos": {"h": 1, "w": 24, "x": 0, "y": 5},
        "collapsed": False,
        "id": panel_id,
    })
    panel_id += 1

    # Pie chart — node states
    p = make_panel(
        "Node State Distribution", "piechart",
        {"h": 8, "w": 8, "x": 0, "y": 6},
        [
            prom_target('count(fleet_cert_node_certified == 1)', "Healthy", instant=True, ref_id="A"),
            prom_target('count(fleet_cert_node_failure_class == 1)', "Maintenance", instant=True, ref_id="B"),
            prom_target('count(fleet_cert_node_failure_class == 2)', "RMA", instant=True, ref_id="C"),
        ],
        options={
            "legend": {"displayMode": "list", "placement": "right"},
            "tooltip": {"mode": "single"},
            "pieType": "donut",
        },
        field_config={
            "defaults": {"color": {"mode": "palette-classic"}},
            "overrides": [
                {"matcher": {"id": "byName", "options": "Healthy"}, "properties": [{"id": "color", "value": {"fixedColor": COLORS["green"]}}]},
                {"matcher": {"id": "byName", "options": "Maintenance"}, "properties": [{"id": "color", "value": {"fixedColor": COLORS["amber"]}}]},
                {"matcher": {"id": "byName", "options": "RMA"}, "properties": [{"id": "color", "value": {"fixedColor": COLORS["red"]}}]},
            ],
        },
        description="Distribution of node states across the fleet"
    )
    p["id"] = panel_id; panel_id += 1
    panels.append(p)

    # State timeline
    p = make_panel(
        "Certification Timeline", "timeseries",
        {"h": 8, "w": 16, "x": 8, "y": 6},
        [
            prom_target('fleet_cert_node_certified', "{{node}}", ref_id="A"),
        ],
        options={
            "legend": {"displayMode": "table", "placement": "right", "calcs": ["lastNotNull"]},
            "tooltip": {"mode": "single"},
        },
        field_config={
            "defaults": {
                "custom": {"drawStyle": "points", "pointSize": 8, "lineWidth": 0},
                "color": {"mode": "thresholds"},
                "thresholds": {"mode": "absolute", "steps": [
                    {"color": COLORS["red"], "value": None},
                    {"color": COLORS["green"], "value": 1},
                ]},
                "mappings": [
                    {"type": "value", "options": {"0": {"text": "FAILED", "color": COLORS["red"]}}},
                    {"type": "value", "options": {"1": {"text": "CERTIFIED", "color": COLORS["green"]}}},
                ],
            },
        },
        description="Certification pass/fail events over time per node"
    )
    p["id"] = panel_id; panel_id += 1
    panels.append(p)

    # ═══════════════════════════════════════════════════════════════
    # Row 3: Test Results Heatmap
    # ═══════════════════════════════════════════════════════════════
    panels.append({
        "type": "row",
        "title": "📊 Test Results Matrix",
        "gridPos": {"h": 1, "w": 24, "x": 0, "y": 14},
        "collapsed": False,
        "id": panel_id,
    })
    panel_id += 1

    # Heatmap — node × test
    p = make_panel(
        "Node × Test Pass/Fail Matrix", "table",
        {"h": 10, "w": 24, "x": 0, "y": 15},
        [
            prom_target(
                'fleet_cert_test_passed',
                "{{node}} — {{test}}",
                instant=True, ref_id="A"
            ),
        ],
        options={
            "showHeader": True,
            "sortBy": [{"displayName": "node", "desc": False}],
        },
        field_config={
            "defaults": {
                "custom": {"align": "center", "displayMode": "color-background-solid"},
                "thresholds": {"mode": "absolute", "steps": [
                    {"color": COLORS["red"], "value": None},
                    {"color": COLORS["green"], "value": 1},
                ]},
                "mappings": [
                    {"type": "value", "options": {"0": {"text": "❌ FAIL", "color": COLORS["red"]}}},
                    {"type": "value", "options": {"1": {"text": "✅ PASS", "color": COLORS["green"]}}},
                ],
            },
        },
        description="Pass/fail status for each test on each node"
    )
    p["id"] = panel_id; panel_id += 1
    panels.append(p)

    # ═══════════════════════════════════════════════════════════════
    # Row 4: GPU Stress Metrics
    # ═══════════════════════════════════════════════════════════════
    panels.append({
        "type": "row",
        "title": "🔥 GPU Stress Metrics",
        "gridPos": {"h": 1, "w": 24, "x": 0, "y": 25},
        "collapsed": False,
        "id": panel_id,
    })
    panel_id += 1

    # DCGMI pass rates
    p = make_panel(
        "DCGMI Diagnostic Pass Rate", "bargauge",
        {"h": 8, "w": 8, "x": 0, "y": 26},
        [
            prom_target('fleet_cert_test_passed{test=~"dcgmi.*"}', "{{node}} — {{test}}", instant=True),
        ],
        field_config={
            "defaults": {
                "max": 1, "min": 0,
                "thresholds": {"mode": "absolute", "steps": [
                    {"color": COLORS["red"], "value": None},
                    {"color": COLORS["green"], "value": 1},
                ]},
            },
        },
        description="DCGMI diagnostic results per node"
    )
    p["id"] = panel_id; panel_id += 1
    panels.append(p)

    # ECC errors
    p = make_panel(
        "ECC Uncorrectable Errors", "timeseries",
        {"h": 8, "w": 8, "x": 8, "y": 26},
        [
            prom_target('fleet_cert_test_metric{test="ecc_check"}', "{{node}}", ref_id="A"),
        ],
        field_config={
            "defaults": {
                "unit": "short",
                "thresholds": {"mode": "absolute", "steps": [
                    {"color": COLORS["green"], "value": None},
                    {"color": COLORS["red"], "value": 1},
                ]},
            },
        },
        description="Uncorrectable ECC errors detected during certification"
    )
    p["id"] = panel_id; panel_id += 1
    panels.append(p)

    # GPU Temperature
    p = make_panel(
        "GPU Temperature During Stress", "timeseries",
        {"h": 8, "w": 8, "x": 16, "y": 26},
        [
            prom_target('fleet_cert_test_metric{test="gpu_temp_check"}', "{{node}}", ref_id="A"),
        ],
        field_config={
            "defaults": {
                "unit": "celsius",
                "thresholds": {"mode": "absolute", "steps": [
                    {"color": COLORS["green"], "value": None},
                    {"color": COLORS["amber"], "value": 80},
                    {"color": COLORS["red"], "value": 90},
                ]},
                "custom": {"thresholdsStyle": {"mode": "line+area"}},
            },
        },
        description="Peak GPU temperature during stress testing"
    )
    p["id"] = panel_id; panel_id += 1
    panels.append(p)

    # ═══════════════════════════════════════════════════════════════
    # Row 5: NCCL Bandwidth
    # ═══════════════════════════════════════════════════════════════
    panels.append({
        "type": "row",
        "title": "📡 NCCL Bandwidth",
        "gridPos": {"h": 1, "w": 24, "x": 0, "y": 34},
        "collapsed": False,
        "id": panel_id,
    })
    panel_id += 1

    nccl_tests = [
        ("AllReduce", "nccl_allreduce"),
        ("AllGather", "nccl_allgather"),
        ("ReduceScatter", "nccl_reducescatter"),
    ]
    for i, (label, metric_prefix) in enumerate(nccl_tests):
        p = make_panel(
            f"NCCL {label} Bus Bandwidth", "bargauge",
            {"h": 8, "w": 8, "x": i * 8, "y": 35},
            [
                prom_target(
                    f'fleet_cert_test_metric{{test=~"{metric_prefix}.*"}}',
                    "{{node}}", instant=True, ref_id="A"
                ),
            ],
            options={
                "orientation": "horizontal",
                "displayMode": "gradient",
            },
            field_config={
                "defaults": {
                    "unit": "GBs",
                    "min": 0,
                    "thresholds": {"mode": "absolute", "steps": [
                        {"color": COLORS["red"], "value": None},
                        {"color": COLORS["amber"], "value": 200},
                        {"color": COLORS["green"], "value": 350},
                    ]},
                },
            },
            description=f"NCCL {label} bus bandwidth per node (GB/s)"
        )
        p["id"] = panel_id; panel_id += 1
        panels.append(p)

    # ═══════════════════════════════════════════════════════════════
    # Row 6: HPL Performance
    # ═══════════════════════════════════════════════════════════════
    panels.append({
        "type": "row",
        "title": "⚡ Compute Performance (HPL)",
        "gridPos": {"h": 1, "w": 24, "x": 0, "y": 43},
        "collapsed": False,
        "id": panel_id,
    })
    panel_id += 1

    p = make_panel(
        "HPL TFLOPS Per Node", "bargauge",
        {"h": 8, "w": 12, "x": 0, "y": 44},
        [
            prom_target('fleet_cert_test_metric{test="hpl_benchmark"}', "{{node}}", instant=True),
        ],
        options={"orientation": "horizontal", "displayMode": "gradient"},
        field_config={
            "defaults": {
                "unit": "TFLOPS",
                "min": 0,
                "thresholds": {"mode": "absolute", "steps": [
                    {"color": COLORS["red"], "value": None},
                    {"color": COLORS["amber"], "value": 30},
                    {"color": COLORS["green"], "value": 55},
                ]},
            },
        },
        description="HPL compute performance per node"
    )
    p["id"] = panel_id; panel_id += 1
    panels.append(p)

    # NeMo inference
    p = make_panel(
        "NeMo Inference TFLOPS", "bargauge",
        {"h": 8, "w": 12, "x": 12, "y": 44},
        [
            prom_target('fleet_cert_test_metric{test="nemo_inference"}', "{{node}}", instant=True),
        ],
        options={"orientation": "horizontal", "displayMode": "gradient"},
        field_config={
            "defaults": {
                "unit": "TFLOPS",
                "min": 0,
                "thresholds": {"mode": "absolute", "steps": [
                    {"color": COLORS["red"], "value": None},
                    {"color": COLORS["green"], "value": 1},
                ]},
            },
        },
        description="NeMo LLM inference throughput per node"
    )
    p["id"] = panel_id; panel_id += 1
    panels.append(p)

    # ═══════════════════════════════════════════════════════════════
    # Row 7: NVBandwidth
    # ═══════════════════════════════════════════════════════════════
    panels.append({
        "type": "row",
        "title": "💾 Memory Bandwidth (nvbandwidth)",
        "gridPos": {"h": 1, "w": 24, "x": 0, "y": 52},
        "collapsed": False,
        "id": panel_id,
    })
    panel_id += 1

    nvbw_tests = [
        ("Host→Device", "nvbandwidth_h2d"),
        ("Device→Device", "nvbandwidth_d2d"),
        ("Bidirectional", "nvbandwidth_bidir"),
    ]
    for i, (label, test_name) in enumerate(nvbw_tests):
        p = make_panel(
            f"nvbandwidth: {label}", "bargauge",
            {"h": 8, "w": 8, "x": i * 8, "y": 53},
            [
                prom_target(
                    f'fleet_cert_test_metric{{test="{test_name}"}}',
                    "{{node}}", instant=True
                ),
            ],
            options={"orientation": "horizontal", "displayMode": "gradient"},
            field_config={
                "defaults": {
                    "unit": "GBs",
                    "min": 0,
                    "thresholds": {"mode": "absolute", "steps": [
                        {"color": COLORS["red"], "value": None},
                        {"color": COLORS["amber"], "value": 100},
                        {"color": COLORS["green"], "value": 500},
                    ]},
                },
            },
            description=f"{label} memory bandwidth per node"
        )
        p["id"] = panel_id; panel_id += 1
        panels.append(p)

    # ═══════════════════════════════════════════════════════════════
    # Row 8: Alerts & State History
    # ═══════════════════════════════════════════════════════════════
    panels.append({
        "type": "row",
        "title": "🔔 Alerts & State History",
        "gridPos": {"h": 1, "w": 24, "x": 0, "y": 61},
        "collapsed": False,
        "id": panel_id,
    })
    panel_id += 1

    # Active alerts
    p = make_panel(
        "Active Fleet Validation Alerts", "table",
        {"h": 8, "w": 12, "x": 0, "y": 62},
        [
            prom_target('ALERTS{alertname=~"Fleet.*"}', "", instant=True),
        ],
        options={"showHeader": True},
        description="Currently firing fleet validation alerts"
    )
    p["id"] = panel_id; panel_id += 1
    panels.append(p)

    # Certification history
    p = make_panel(
        "Certification History (Last 7 Days)", "timeseries",
        {"h": 8, "w": 12, "x": 12, "y": 62},
        [
            prom_target('fleet_cert_nodes_passed', "Passed", ref_id="A"),
            prom_target('fleet_cert_nodes_failed', "Failed", ref_id="B"),
        ],
        options={
            "legend": {"displayMode": "list", "placement": "bottom"},
        },
        field_config={
            "defaults": {"custom": {"fillOpacity": 30}},
            "overrides": [
                {"matcher": {"id": "byName", "options": "Passed"}, "properties": [{"id": "color", "value": {"fixedColor": COLORS["green"]}}]},
                {"matcher": {"id": "byName", "options": "Failed"}, "properties": [{"id": "color", "value": {"fixedColor": COLORS["red"]}}]},
            ],
        },
        description="Daily certification pass/fail trends"
    )
    p["id"] = panel_id; panel_id += 1
    panels.append(p)

    # ═══════════════════════════════════════════════════════════════
    # Assemble Dashboard
    # ═══════════════════════════════════════════════════════════════
    dashboard = {
        "id": None,
        "uid": "fleet-validation-framework",
        "title": "Continuous Monitoring and Fleet Validation Framework",
        "description": "Daily proactive certification dashboard for BCM-managed GPU fleet (H200/B200)",
        "tags": ["fleet-validation", "gpu", "certification", "bcm", "nccl"],
        "timezone": "utc",
        "editable": True,
        "graphTooltip": 1,
        "refresh": "5m",
        "schemaVersion": 39,
        "version": 1,
        "time": {"from": "now-7d", "to": "now"},
        "templating": {
            "list": [
                {
                    "name": "DS_PROMETHEUS",
                    "type": "datasource",
                    "query": "prometheus",
                    "current": {"text": "Prometheus", "value": "Prometheus"},
                },
                {
                    "name": "suite",
                    "type": "custom",
                    "query": "daily-quick,gpu-burn,nccl-multinode,full-certification",
                    "current": {"text": "daily-quick", "value": "daily-quick"},
                    "label": "Test Suite",
                },
                {
                    "name": "node",
                    "type": "query",
                    "query": 'label_values(fleet_cert_node_certified, node)',
                    "datasource": {"type": "prometheus", "uid": "${DS_PROMETHEUS}"},
                    "multi": True,
                    "includeAll": True,
                    "label": "Node",
                },
            ],
        },
        "annotations": {
            "list": [
                {
                    "name": "Certification Runs",
                    "datasource": {"type": "prometheus", "uid": "${DS_PROMETHEUS}"},
                    "expr": "changes(fleet_cert_last_run_timestamp[1h]) > 0",
                    "titleFormat": "Certification Run",
                    "textFormat": "Suite: {{suite}}",
                    "iconColor": COLORS["blue"],
                    "enable": True,
                },
            ],
        },
        "panels": panels,
    }

    return dashboard


if __name__ == "__main__":
    dashboard = generate_dashboard()
    with open(OUTPUT_PATH, "w") as f:
        json.dump(dashboard, f, indent=2)
    print(f"✅ Dashboard generated: {OUTPUT_PATH}")
    print(f"   Panels: {len(dashboard['panels'])}")
    print(f"   Title: {dashboard['title']}")

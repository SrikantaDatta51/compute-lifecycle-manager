#!/usr/bin/env python3
"""
Generate Grafana dashboard JSON for BCM Process Metrics.
Every panel has a description explaining how the metric is calculated
with references to Linux kernel scheduling and /proc filesystem.
"""
import json
import sys

# ─── Helpers ─────────────────────────────────────────────────────────

def panel(title, ptype, targets, gridPos, overrides=None,
          thresholds=None, unit="", legend=True, stack=False,
          description="", mappings=None, decimals=None,
          orientation="auto", text_mode="auto", color_mode="value",
          graph_mode="none", reduce_calc="lastNotNull"):
    p = {
        "title": title,
        "type": ptype,
        "datasource": {"type": "prometheus", "uid": "${DS_PROMETHEUS}"},
        "targets": targets,
        "gridPos": gridPos,
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "thresholds": thresholds or {"mode": "absolute", "steps": [
                    {"color": "green", "value": None}
                ]},
            },
            "overrides": overrides or [],
        },
        "options": {},
    }
    if description:
        p["description"] = description
    if decimals is not None:
        p["fieldConfig"]["defaults"]["decimals"] = decimals

    if ptype == "stat":
        p["options"] = {
            "reduceOptions": {"calcs": [reduce_calc], "fields": "", "values": False},
            "textMode": text_mode,
            "colorMode": color_mode,
            "graphMode": graph_mode,
            "orientation": orientation,
        }
    elif ptype == "timeseries":
        p["options"]["legend"] = {
            "displayMode": "table" if legend else "hidden",
            "placement": "bottom",
            "calcs": ["min", "max", "mean", "lastNotNull"] if legend else [],
        }
        if stack:
            p["fieldConfig"]["defaults"]["custom"] = {"stacking": {"mode": "normal"}}
    elif ptype == "table":
        p["options"]["showHeader"] = True
        p["options"]["sortBy"] = [{"displayName": "CPU %", "desc": True}]
    elif ptype == "gauge":
        p["options"]["reduceOptions"] = {"calcs": [reduce_calc], "fields": "", "values": False}
    elif ptype == "bargauge":
        p["options"] = {
            "reduceOptions": {"calcs": [reduce_calc], "fields": "", "values": False},
            "orientation": "horizontal",
            "displayMode": "gradient",
        }
    if mappings:
        p["fieldConfig"]["defaults"]["mappings"] = mappings
    return p


def target(expr, legend="", instant=False, fmt="table"):
    t = {
        "expr": expr,
        "legendFormat": legend,
        "datasource": {"type": "prometheus", "uid": "${DS_PROMETHEUS}"},
    }
    if instant:
        t["instant"] = True
        t["range"] = False
    if fmt:
        t["format"] = fmt
    return t


# ─── Dashboard Builder ──────────────────────────────────────────────

panels = []
y = 0  # vertical position

# ━━━ ROW 1: Overview Stats ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

panels.append(panel(
    "CPU Contention",
    "stat",
    [target('bcm_cpu_contention_score', instant=True, fmt="")],
    {"x": 0, "y": y, "w": 4, "h": 4},
    description=(
        "**How it's calculated:**\n\n"
        "Contention = `total_CPU_%_all_processes / (num_cores × 100)`\n\n"
        "In Linux, the CFS (Completely Fair Scheduler) distributes CPU time across all "
        "runnable tasks. When the total demanded CPU exceeds available cores, processes "
        "compete for time slices — this is contention.\n\n"
        "- **0** = No contention. Total CPU demand fits within available cores.\n"
        "- **1** = Full contention. Processes demand 100% of every core.\n\n"
        "Source: Derived from `/proc/stat` total CPU and `ps` aggregate CPU.\n"
        "If this reaches **1**, tasks are waiting in the run queue and experiencing "
        "scheduling latency — check `vmstat` column `r` for run queue depth."
    ),
    thresholds={"mode": "absolute", "steps": [
        {"color": "green", "value": None},
        {"color": "#EAB839", "value": 0.5},
        {"color": "red", "value": 0.8},
    ]},
    mappings=[
        {"type": "range", "options": {"from": 0, "to": 0.49, "result": {"text": "NO CONTENTION", "color": "green"}}},
        {"type": "range", "options": {"from": 0.5, "to": 0.79, "result": {"text": "MODERATE", "color": "#EAB839"}}},
        {"type": "range", "options": {"from": 0.8, "to": 999, "result": {"text": "CONTENTION!", "color": "red"}}},
    ],
    color_mode="background",
    text_mode="value_and_name",
    decimals=2,
))

panels.append(panel(
    "Total Cores",
    "stat",
    [target('bcm_node_cpu_cores_total', instant=True, fmt="")],
    {"x": 4, "y": y, "w": 4, "h": 4},
    description=(
        "**How it's calculated:**\n\n"
        "`nproc` — number of logical CPU cores available to the OS.\n\n"
        "On systems with HyperThreading, this is 2× physical cores. "
        "Each core can independently run one thread at a time through the "
        "Linux CFS scheduler. This is the denominator for contention scoring."
    ),
    color_mode="value",
    graph_mode="none",
    decimals=0,
))

panels.append(panel(
    "Weka Core Limit Alert",
    "stat",
    [target('bcm_weka_core_limit_exceeded', instant=True, fmt="")],
    {"x": 8, "y": y, "w": 4, "h": 4},
    description=(
        "**How it's calculated:**\n\n"
        "`1` if total CPU cores consumed by Weka processes > 17, else `0`.\n\n"
        "Weka.IO storage processes pin themselves to specific CPU cores using "
        "`taskset`/`cpuset`. If Weka exceeds 17 cores, it starves other services "
        "(Slurm, NVIDIA drivers) of CPU time.\n\n"
        "- **0 = OK** — Weka within limit\n"
        "- **1 = EXCEEDED** — Weka using too many cores, other services impacted"
    ),
    thresholds={"mode": "absolute", "steps": [
        {"color": "green", "value": None},
        {"color": "red", "value": 1},
    ]},
    mappings=[
        {"type": "value", "options": {"0": {"text": "✅ OK (within 17-core limit)", "color": "green"}}},
        {"type": "value", "options": {"1": {"text": "🚨 EXCEEDED 17-CORE LIMIT", "color": "red"}}},
    ],
    color_mode="background",
    text_mode="value_and_name",
    decimals=0,
))

panels.append(panel(
    "Weka Core Limit",
    "gauge",
    [target('sum(bcm_service_cpu_cores_total{service="weka"})', '{{hostname}}', instant=True, fmt="")],
    {"x": 12, "y": y, "w": 4, "h": 4},
    description=(
        "**How it's calculated:**\n\n"
        "Sum of `CPU% / 100` for all processes matching `weka*`.\n\n"
        "Example: 17 Weka I/O threads each at 100% = 17.0 cores used.\n"
        "Threshold set at 17 cores (the configured limit)."
    ),
    thresholds={"mode": "absolute", "steps": [
        {"color": "green", "value": None},
        {"color": "#EAB839", "value": 14},
        {"color": "red", "value": 17},
    ]},
    unit="short",
    decimals=1,
))

panels.append(panel(
    "Active Processes",
    "stat",
    [target('count(bcm_process_cpu_percent > 0)', instant=True, fmt="")],
    {"x": 16, "y": y, "w": 4, "h": 4},
    description=(
        "**How it's calculated:**\n\n"
        "Count of processes with CPU% > 0 from `ps -eo %cpu`.\n\n"
        "This shows processes actively consuming CPU scheduling time. "
        "The Linux scheduler only allocates time slices to processes in the "
        "`TASK_RUNNING` state. Sleeping/idle processes are excluded."
    ),
    color_mode="value",
    decimals=0,
))

panels.append(panel(
    "Process Count by Service",
    "stat",
    [target('bcm_service_process_count', '{{service}}', instant=True, fmt="")],
    {"x": 20, "y": y, "w": 4, "h": 4},
    description=(
        "**How it's calculated:**\n\n"
        "Count of all processes (including idle) grouped by service classification.\n\n"
        "Classification rules:\n"
        "- `weka` = weka*, WekaIO*\n"
        "- `slurm` = slurm*, srun\n"
        "- `bcm` = cmd, cmsh\n"
        "- `mysql` = mysqld\n"
        "- `kernel` = kworker/*, rcu_*, cpuhp/*\n"
        "- Others = shown by actual process name"
    ),
    color_mode="value",
    decimals=0,
))

y += 4

# ━━━ ROW 2: Process Table — the main view ━━━━━━━━━━━━━━━━━━━━━━━━━

panels.append(panel(
    "📋 Process Details — CPU%, Cores Used, Threads, Memory",
    "table",
    [
        target(
            'topk(25, bcm_process_cpu_percent)',
            instant=True,
            fmt="table"
        ),
        target(
            'bcm_process_cpu_cores_used',
            instant=True,
            fmt="table"
        ),
        target(
            'bcm_process_threads',
            instant=True,
            fmt="table"
        ),
        target(
            'bcm_process_rss_bytes',
            instant=True,
            fmt="table"
        ),
        target(
            'bcm_process_mem_percent',
            instant=True,
            fmt="table"
        ),
    ],
    {"x": 0, "y": y, "w": 24, "h": 10},
    description=(
        "**How each column is calculated:**\n\n"
        "| Column | Source | Meaning |\n"
        "|--------|--------|---------|\n"
        "| **CPU %** | `ps -eo %cpu` | % of ONE core's time used. 100% = 1 full core. 400% = 4 cores. |\n"
        "| **Cores Used** | `CPU% / 100` | How many logical cores this process is using. Derived from CPU%. |\n"
        "| **Threads** | `ps -eo nlwp` | Number of kernel-scheduled threads (NLWP = Number of Light Weight Processes). Each thread gets its own time slice from the CFS scheduler. |\n"
        "| **RSS (Memory)** | `ps -eo rss` × 1024 | Resident Set Size — physical RAM actually mapped to the process. Does NOT include swap or shared pages counted elsewhere. |\n"
        "| **Mem %** | `ps -eo %mem` | RSS / total physical RAM × 100. |\n"
        "| **Service** | Pattern match | Classification: weka, slurm, nvidia, bcm, mysql, nfs, system, kernel, or actual process name. |\n\n"
        "**Linux scheduling context:** Each thread is scheduled independently by the CFS (Completely Fair Scheduler). "
        "A process with 83 threads (like `cmd`) doesn't use 83 cores — most threads are sleeping. "
        "Only threads in `TASK_RUNNING` state consume CPU time. The CPU% shows actual utilization."
    ),
    overrides=[
        {
            "matcher": {"id": "byName", "options": "Value #A"},
            "properties": [{"id": "displayName", "value": "CPU %"}, {"id": "unit", "value": "percent"}]
        },
        {
            "matcher": {"id": "byName", "options": "Value #B"},
            "properties": [{"id": "displayName", "value": "Cores Used"}, {"id": "decimals", "value": 2}]
        },
        {
            "matcher": {"id": "byName", "options": "Value #C"},
            "properties": [{"id": "displayName", "value": "Threads"}]
        },
        {
            "matcher": {"id": "byName", "options": "Value #D"},
            "properties": [{"id": "displayName", "value": "RSS"}, {"id": "unit", "value": "bytes"}]
        },
        {
            "matcher": {"id": "byName", "options": "Value #E"},
            "properties": [{"id": "displayName", "value": "Mem %"}, {"id": "unit", "value": "percent"}]
        },
    ],
))

y += 10

# ━━━ ROW 3: Per-Core CPU Usage ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

panels.append(panel(
    "🔲 Per-Core CPU Usage (each core individually)",
    "timeseries",
    [target('bcm_cpu_core_usage_percent', 'Core {{core}}', fmt="")],
    {"x": 0, "y": y, "w": 16, "h": 8},
    description=(
        "**How it's calculated:**\n\n"
        "Two snapshots of `/proc/stat` taken 1 second apart:\n"
        "```\n"
        "cpu0  user nice system idle iowait irq softirq steal\n"
        "```\n"
        "Usage = `(user₂+system₂ - user₁-system₁) / (total₂ - total₁) × 100`\n\n"
        "Each line in `/proc/stat` is a separate CPU core. Core 0 is the first logical CPU.\n\n"
        "**What to look for:**\n"
        "- One core at 100% while others idle → single-threaded bottleneck\n"
        "- All cores at 100% → heavy multi-threaded workload (or contention)\n"
        "- Even distribution → good scheduling, CFS is balancing load\n\n"
        "**OS Context:** The Linux kernel tracks CPU ticks per core. Each tick is "
        "1/CONFIG_HZ seconds (typically 1ms). We diff two readings to get the "
        "percentage of ticks spent on user+system work vs idle."
    ),
    thresholds={"mode": "absolute", "steps": [
        {"color": "green", "value": None},
        {"color": "#EAB839", "value": 70},
        {"color": "red", "value": 90},
    ]},
    unit="percent",
))

panels.append(panel(
    "Per-Core Current",
    "bargauge",
    [target('bcm_cpu_core_usage_percent', 'Core {{core}}', instant=True, fmt="")],
    {"x": 16, "y": y, "w": 8, "h": 8},
    description=(
        "**Bar gauge** showing the latest per-core CPU usage.\n\n"
        "Sorted by core ID. Green < 70%, Yellow 70-90%, Red > 90%.\n\n"
        "If one core is pegged at 100% — find the single-threaded process "
        "using `perf top` or `pidstat -u 1`."
    ),
    thresholds={"mode": "absolute", "steps": [
        {"color": "green", "value": None},
        {"color": "#EAB839", "value": 70},
        {"color": "red", "value": 90},
    ]},
    unit="percent",
))

y += 8

# ━━━ ROW 3b: Process-to-Core Mapping (HEATMAP) ━━━━━━━━━━━━━━━━━━━━

panels.append(panel(
    "🗺️ Process → Core Mapping (which process is on which core)",
    "timeseries",
    [target('bcm_process_core_map', '{{process}} → Core {{core}}', fmt="")],
    {"x": 0, "y": y, "w": 16, "h": 8},
    description=(
        "**How it's calculated:**\n\n"
        "`ps -eo pid,comm,%cpu,psr` — the PSR column is the **processor** (core) "
        "that the process last executed on.\n\n"
        "**Linux Kernel Source:**\n"
        "- PSR = `/proc/[pid]/stat` field 39 (`processor`)\n"
        "- This is the core number where the task was last scheduled by the CFS\n"
        "- Updated every context switch when the scheduler picks a core via `select_task_rq_fair()`\n\n"
        "**How to read this panel:**\n"
        "- Each line = one process, plotted by CPU% over time\n"
        "- Legend shows `process → Core N` — which core it's currently on\n"
        "- If a process jumps between cores → not pinned (normal CFS behavior)\n"
        "- If a process stays on one core → either pinned via `taskset` or CPU affinity\n\n"
        "**CPU Affinity:**\n"
        "- `taskset -p <pid>` shows the affinity mask\n"
        "- Weka pins I/O threads to specific cores via `cpuset`\n"
        "- Processes without explicit pinning can migrate between cores freely\n"
        "- The scheduler moves tasks to balance load across NUMA nodes"
    ),
    unit="percent",
))

panels.append(panel(
    "📊 Processes Per Core (load distribution)",
    "bargauge",
    [target('bcm_core_process_count', 'Core {{core}}', instant=True, fmt="")],
    {"x": 16, "y": y, "w": 8, "h": 8},
    description=(
        "**How it's calculated:**\n\n"
        "Count of userspace processes assigned to each core from `ps -eo psr`.\n\n"
        "**What this tells you:**\n"
        "- Even distribution → CFS is load balancing properly\n"
        "- One core with many more processes → possible pinning or imbalance\n"
        "- Core 0 often has more because boot processes default there\n\n"
        "**Context:** The Linux scheduler distributes processes across cores "
        "considering NUMA topology, cache locality, and load. "
        "A core with 50 processes doesn't mean it's overloaded — "
        "most may be sleeping. Check per-core CPU% for actual load."
    ),
    thresholds={"mode": "absolute", "steps": [
        {"color": "green", "value": None},
        {"color": "#EAB839", "value": 30},
        {"color": "red", "value": 50},
    ]},
))

y += 8

# ━━━ ROW 3c: Process-Core Mapping Table ━━━━━━━━━━━━━━━━━━━━━━━━━━━

panels.append(panel(
    "🔍 Process-to-Core Detail Table (snapshot)",
    "table",
    [
        target(
            'bcm_process_core_map',
            instant=True,
            fmt="table"
        ),
    ],
    {"x": 0, "y": y, "w": 24, "h": 8},
    description=(
        "**How it's calculated:**\n\n"
        "Snapshot of all active processes and which CPU core they're currently "
        "scheduled on. Columns:\n\n"
        "| Column | Source | Meaning |\n"
        "|--------|--------|---------|\n"
        "| **Process** | `ps -eo comm` | Process command name |\n"
        "| **Core** | `ps -eo psr` | CPU core number (0-indexed). From `/proc/[pid]/stat` field 39. |\n"
        "| **CPU %** | `ps -eo %cpu` | Percentage of time slice used on that core |\n"
        "| **PID** | `ps -eo pid` | Process ID |\n\n"
        "**Why this matters:**\n"
        "- Shows which processes share a core (contention at core level)\n"
        "- Weka threads should be on dedicated cores (not sharing with Slurm)\n"
        "- If two heavy processes share one core while other cores are idle → misconfigured affinity\n\n"
        "**How the kernel schedules:**\n"
        "1. Each core has a run queue (CFS red-black tree)\n"
        "2. `select_task_rq_fair()` picks the best core for a waking task\n"
        "3. Considers: CPU idle state, cache warmth, NUMA node, wake_affine heuristic\n"
        "4. Once assigned, the core's scheduler runs the task in `vruntime` order"
    ),
    overrides=[
        {
            "matcher": {"id": "byName", "options": "Value"},
            "properties": [{"id": "displayName", "value": "CPU %"}, {"id": "unit", "value": "percent"}]
        },
    ],
))

y += 8

# ━━━ ROW 4: Service-Level Core Usage ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

panels.append(panel(
    "🏷️ Cores Used per Service (stacked area)",
    "timeseries",
    [target('bcm_service_cpu_cores_total', '{{service}}', fmt="")],
    {"x": 0, "y": y, "w": 12, "h": 8},
    description=(
        "**How it's calculated:**\n\n"
        "For each service class, sum `CPU% / 100` of all matching processes.\n\n"
        "Example: 3 slurm processes at 0.1% each → `0.003` cores total.\n\n"
        "This tells you which service is consuming compute capacity.\n"
        "On production nodes with Weka + Slurm jobs, you'll see:\n"
        "- `weka` consuming ~17 cores (pinned I/O threads)\n"
        "- `slurm` job consuming remaining cores\n"
        "- `system` + `kernel` using negligible CPU\n\n"
        "**Warning sign:** weka + slurm + nvidia together exceeding total core count."
    ),
    stack=True,
    unit="short",
))

panels.append(panel(
    "Thread Count per Service",
    "timeseries",
    [target('bcm_service_process_count', '{{service}}', fmt="")],
    {"x": 12, "y": y, "w": 12, "h": 8},
    description=(
        "**How it's calculated:**\n\n"
        "Count of processes per service class from `ps -eo comm`.\n\n"
        "**Important:** Thread count ≠ CPU usage. A process can have 100 threads "
        "but only 2 are actively running (rest are sleeping in `TASK_INTERRUPTIBLE` state, "
        "waiting for I/O, locks, or timers).\n\n"
        "Example: `cmd` (BCM daemon) has 83 threads but uses only 0.7% CPU.\n\n"
        "**What matters is CPU%, not thread count.** But sudden thread growth "
        "can indicate issues (thread leaks, fork bombs)."
    ),
))

y += 8

# ━━━ ROW 5: Top Processes ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

panels.append(panel(
    "🔥 Top Processes by CPU% (over time)",
    "timeseries",
    [target('topk(10, bcm_process_cpu_percent)', '{{process}} ({{service}})', fmt="")],
    {"x": 0, "y": y, "w": 12, "h": 8},
    description=(
        "**How it's calculated:**\n\n"
        "Top 10 processes by CPU% from `ps -eo %cpu`, tracked over time.\n\n"
        "**CPU% in Linux:**\n"
        "- `ps` CPU% = ratio of CPU time to wall-clock time since process start\n"
        "- A multi-threaded process CAN exceed 100% (e.g. 400% = using 4 cores)\n"
        "- Single-threaded process maxes at 100% (one core fully utilized)\n\n"
        "**What to look for:**\n"
        "- Sudden spikes → new workload or runaway process\n"
        "- Sustained high CPU → expected for Weka/Slurm jobs\n"
        "- `cmd` (BCM) or `mysqld` consistently high → BCM overhead issue"
    ),
    unit="percent",
))

panels.append(panel(
    "🧵 Top Processes by Thread Count (over time)",
    "timeseries",
    [target('topk(10, bcm_process_threads)', '{{process}} ({{service}})', fmt="")],
    {"x": 12, "y": y, "w": 12, "h": 8},
    description=(
        "**How it's calculated:**\n\n"
        "Top 10 processes by thread count (`ps -eo nlwp`), tracked over time.\n\n"
        "**Linux Thread Model:**\n"
        "- Each thread = kernel task with its own `task_struct`\n"
        "- Threads share address space but get independent scheduling\n"
        "- NLWP = Number of Light Weight Processes (Linux threads via `clone()`)\n"
        "- Thread count from `/proc/[pid]/status` → `Threads:` field\n\n"
        "**Context:**\n"
        "- `cmd` (BCM daemon): ~83 threads (management, monitoring, RPC handlers)\n"
        "- `slurmctld`: ~50 threads (job scheduling, node communication)\n"
        "- `mysqld`: ~45 threads (connection pool, InnoDB threads)\n\n"
        "**Alert:** Rapid thread growth → possible thread leak or fork bomb."
    ),
))

y += 8

# ━━━ ROW 6: Memory + Contention ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

panels.append(panel(
    "💾 Top Processes by RSS Memory",
    "timeseries",
    [target('topk(10, bcm_process_rss_bytes)', '{{process}} ({{service}})', fmt="")],
    {"x": 0, "y": y, "w": 12, "h": 8},
    description=(
        "**How it's calculated:**\n\n"
        "RSS (Resident Set Size) = physical RAM pages currently mapped to the process.\n"
        "Source: `ps -eo rss` × 1024 (ps reports in KB, we convert to bytes).\n\n"
        "**Linux Memory Model:**\n"
        "- RSS = actual physical pages in RAM (not swap, not shared libraries counted elsewhere)\n"
        "- From `/proc/[pid]/status` → `VmRSS:` field\n"
        "- Does NOT include file-backed pages that can be reclaimed\n"
        "- Does NOT include shared memory counted in other processes\n\n"
        "**Typical values:**\n"
        "- `mysqld`: ~1GB (InnoDB buffer pool)\n"
        "- `cmd` (BCM): ~200MB\n"
        "- `slurmctld`: ~25MB"
    ),
    unit="bytes",
))

panels.append(panel(
    "📊 Contention Score History",
    "timeseries",
    [target('bcm_cpu_contention_score', '{{hostname}}', fmt="")],
    {"x": 12, "y": y, "w": 12, "h": 8},
    description=(
        "**How it's calculated:**\n\n"
        "`contention = total_CPU_all_procs / (num_cores × 100)`\n\n"
        "This tracks the ratio over time. Think of it as:\n"
        "- How many cores worth of work is being demanded\n"
        "- Divided by how many cores are available\n\n"
        "**OS Scheduling Context:**\n"
        "When contention > 1.0, the CFS scheduler cannot give every runnable "
        "task a full time slice. Tasks start waiting in the run queue (`/proc/loadavg` "
        "field 1). Response times increase because:\n\n"
        "1. Task arrives in `TASK_RUNNING` state\n"
        "2. CFS puts it in the red-black tree ordered by `vruntime`\n"
        "3. If all cores are busy, it waits for the next scheduling tick\n"
        "4. The wait time = scheduling latency\n\n"
        "**Thresholds:**\n"
        "- 0.0 – 0.5: Green (plenty of headroom)\n"
        "- 0.5 – 0.8: Yellow (moderate load)\n"
        "- 0.8+: Red (contention, tasks waiting for CPU)"
    ),
    thresholds={"mode": "absolute", "steps": [
        {"color": "green", "value": None},
        {"color": "#EAB839", "value": 0.5},
        {"color": "red", "value": 0.8},
    ]},
    decimals=2,
))

y += 8

# ━━━ ROW 7: Weka + Slurm Contention Detail ━━━━━━━━━━━━━━━━━━━━━━━

panels.append(panel(
    "⚡ Weka vs Slurm Cores (contention check)",
    "timeseries",
    [
        target('bcm_service_cpu_cores_total{service="weka"}', 'Weka Cores', fmt=""),
        target('bcm_service_cpu_cores_total{service="slurm"}', 'Slurm Cores', fmt=""),
        target('bcm_node_cpu_cores_total', 'Total Available Cores', fmt=""),
    ],
    {"x": 0, "y": y, "w": 12, "h": 8},
    description=(
        "**Why this panel matters:**\n\n"
        "On DGX/GPU nodes, Weka I/O processes pin to specific cores using `cpuset`. "
        "Slurm jobs use the remaining cores. If `weka_cores + slurm_cores > total_cores`, "
        "they're fighting over the same physical cores.\n\n"
        "**How to read:**\n"
        "- Green line (total) should always be above the stacked weka+slurm area\n"
        "- If stacked area touches green line → approaching contention\n"
        "- If stacked area exceeds green line → active contention\n\n"
        "**Fix:** Increase Weka core limit headroom or adjust Slurm `--cpus-per-task`."
    ),
    unit="short",
))

panels.append(panel(
    "📈 Weka Core Usage History (vs 17-core limit)",
    "timeseries",
    [
        target('bcm_service_cpu_cores_total{service="weka"}', 'Weka Cores Used', fmt=""),
        target('bcm_weka_core_limit', 'Limit (17)', fmt=""),
    ],
    {"x": 12, "y": y, "w": 12, "h": 8},
    description=(
        "**How it's calculated:**\n\n"
        "Sum of `CPU% / 100` for all `weka*` processes vs the configured limit (17 cores).\n\n"
        "Weka.IO uses a poll-mode driver model — each I/O thread spins at 100% CPU "
        "on its assigned core (similar to DPDK). This is by design for low-latency storage.\n\n"
        "**Expected behavior:**\n"
        "- In production: Weka ~17.0 cores (flat line just below limit)\n"
        "- In this lab: 0 cores (no Weka installed)\n\n"
        "**Alert fires when:** weka cores > 17 core limit."
    ),
    thresholds={"mode": "absolute", "steps": [
        {"color": "green", "value": None},
        {"color": "red", "value": 17},
    ]},
    unit="short",
))

# ─── Assemble Dashboard ─────────────────────────────────────────────

dashboard = {
    "__inputs": [
        {"name": "DS_PROMETHEUS", "type": "datasource", "pluginId": "prometheus", "pluginName": "Prometheus"},
    ],
    "uid": "bcm-process-metrics",
    "title": "BCM Process Metrics — CPU, Cores, Threads, Contention",
    "tags": ["bcm", "process", "cpu", "contention", "weka"],
    "timezone": "browser",
    "editable": True,
    "refresh": "15s",
    "time": {"from": "now-30m", "to": "now"},
    "panels": panels,
    "templating": {
        "list": [
            {
                "name": "hostname",
                "type": "query",
                "datasource": {"type": "prometheus", "uid": "${DS_PROMETHEUS}"},
                "query": 'label_values(bcm_node_info, hostname)',
                "refresh": 2,
                "includeAll": True,
                "multi": True,
                "current": {"text": "All", "value": "$__all"},
            },
        ],
    },
    "annotations": {"list": []},
    "schemaVersion": 39,
    "version": 1,
}

# ─── Write ───────────────────────────────────────────────────────────

outfile = "scripts/bcm-process-metrics-dashboard.json"
with open(outfile, "w") as f:
    json.dump(dashboard, f, indent=2)

print(f"Dashboard saved to {outfile}")
print(f"Panels: {len(panels)}")
print(f"Rows: {y // 8}")
print(f"\nPanel descriptions:")
for p in panels:
    desc = p.get("description", "")
    has_desc = "✅" if desc else "❌"
    print(f"  {has_desc} {p['title']}")
print(f"\nImport into Grafana → Dashboards → Import → Upload JSON file")

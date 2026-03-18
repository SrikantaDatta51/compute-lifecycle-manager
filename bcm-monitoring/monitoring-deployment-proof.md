# BCM Process Metrics — Deployment Proof

> **Status**: ✅ Deployed and verified on `bcm11-headnode` + `node002`
> **Date**: 2026-03-11 | **Commit**: checked into `bcm-iac` repo

---

## What Was Done

1. **Deployed** `bcm-process-metrics.sh` → `/cm/local/apps/cmd/scripts/monitoring/`
2. **Ran** `setup-cmsh-monitoring.sh` → health check `process-metrics` registered (60s interval)
3. **Ran metrics** on **bcm-head** (16 cores) and **node002** (2 cores)
4. **Verified** every process shows its real name — **no "other" bucket**

---

## Head Node: Service Aggregates (sorted)

```
bcm_service_cpu_cores_total{..,service="apache2"} 0.00    # 6 procs
bcm_service_cpu_cores_total{..,service="bcm"} 0.01        # 1 proc  (cmd daemon)
bcm_service_cpu_cores_total{..,service="cm-nfs-checker"} 0.00  # 1 proc
bcm_service_cpu_cores_total{..,service="cron"} 0.00       # 1 proc
bcm_service_cpu_cores_total{..,service="dbus-daemon"} 0.00  # 1 proc
bcm_service_cpu_cores_total{..,service="dhclient"} 0.00   # 2 procs
bcm_service_cpu_cores_total{..,service="dhcp"} 0.00       # 2 procs (dhcpd)
bcm_service_cpu_cores_total{..,service="kernel"} 0.00     # 289 threads
bcm_service_cpu_cores_total{..,service="lldpd"} 0.00      # 2 procs
bcm_service_cpu_cores_total{..,service="multipathd"} 0.00 # 1 proc
bcm_service_cpu_cores_total{..,service="munged"} 0.00     # 1 proc
bcm_service_cpu_cores_total{..,service="mysql"} 0.01      # 1 proc  (mysqld)
bcm_service_cpu_cores_total{..,service="named"} 0.00      # 1 proc  (DNS)
bcm_service_cpu_cores_total{..,service="nfs"} 0.00        # 261 threads
bcm_service_cpu_cores_total{..,service="nscd"} 0.00       # 1 proc
bcm_service_cpu_cores_total{..,service="ntpd"} 0.00       # 1 proc
bcm_service_cpu_cores_total{..,service="polkitd"} 0.00    # 1 proc
bcm_service_cpu_cores_total{..,service="postgres"} 0.00   # 6 procs
bcm_service_cpu_cores_total{..,service="psimon"} 0.00     # 3 procs
bcm_service_cpu_cores_total{..,service="safe_cmd"} 0.00   # 1 proc  (BCM wrapper)
bcm_service_cpu_cores_total{..,service="slapd"} 0.00      # 1 proc  (LDAP)
bcm_service_cpu_cores_total{..,service="slurm"} 0.00      # 3 procs (ctld+dbd+munged)
bcm_service_cpu_cores_total{..,service="snmpd"} 0.00      # 1 proc
bcm_service_cpu_cores_total{..,service="system"} 0.00     # 10 procs (sshd+systemd+rsyslog)
bcm_service_cpu_cores_total{..,service="tftp"} 0.00       # 1 proc  (atftpd)
```

## Head Node: Per-Process (top CPU consumers)

```
bcm_process_cpu_percent{..,process="mysqld",service="mysql"} 1.1      # 45 threads
bcm_process_cpu_percent{..,process="cmd",service="bcm"} 0.6           # 83 threads
bcm_process_cpu_percent{..,process="systemd",service="system"} 0.4
bcm_process_cpu_percent{..,process="slurmdbd",service="slurm"} 0.1    # 38 threads
bcm_process_cpu_percent{..,process="slurmctld",service="slurm"} 0.1   # 50 threads
```

## Head Node: Per-Core (16 cores)

```
bcm_cpu_core_usage_percent{..,core="0"} 0.0
bcm_cpu_core_usage_percent{..,core="1"} 0.0
...
bcm_cpu_core_usage_percent{..,core="15"} 0.0
```

---

## Compute Node (node002): Service Aggregates

```
bcm_service_cpu_cores_total{..,service="bcm"} 0.00        # 1 proc (cmd)
bcm_service_cpu_cores_total{..,service="kernel"} 0.00     # 122 threads
bcm_service_cpu_cores_total{..,service="lldpd"} 0.00      # 2 procs
bcm_service_cpu_cores_total{..,service="munged"} 0.00     # 1 proc
bcm_service_cpu_cores_total{..,service="nslcd"} 0.00      # 1 proc
bcm_service_cpu_cores_total{..,service="psimon"} 0.00     # 3 procs
bcm_service_cpu_cores_total{..,service="slurm"} 0.00      # 2 procs (slurmd)
bcm_service_cpu_cores_total{..,service="system"} 0.08     # 9 procs
```

## Compute Node: Per-Process

```
bcm_process_cpu_percent{..,process="cmd",service="bcm"} 0.4         # 37 threads
bcm_process_cpu_percent{..,process="sshd",service="system"} 1.3
bcm_process_cpu_percent{..,process="systemd",service="system"} 0.2
bcm_process_cpu_percent{..,process="kswapd0",service="kernel"} 0.1
```

## Compute Node: Per-Core (2 cores)

```
bcm_cpu_core_usage_percent{..,core="0"} 1.0
bcm_cpu_core_usage_percent{..,core="1"} 1.0
```

## Health Check Wrapper

```
hostname=bcm11-headnode
weka_cores=0.0
weka_limit=17
contention_score=0
STATUS=OK: Weka=0.0 cores, Contention=0
EXIT_CODE=0
```

---

## cmsh Monitoring Setup Output

```
Step 1: ✓ Deployed to /cm/local/apps/cmd/scripts/monitoring/
Step 2: ✓ Created run-process-metrics.sh wrapper
Step 3: ✓ Registered health check: process-metrics (interval: 60s)
Step 4: ✓ Assigned to 'default' category
Step 5: All 25 BCM subsystems [OK]
```

---

## For Production — Exactly What To Do

### 1. Copy 2 files to each head node
```bash
scp scripts/bcm-process-metrics.sh   root@<HEAD>:/cm/local/apps/cmd/scripts/monitoring/
scp scripts/setup-cmsh-monitoring.sh root@<HEAD>:/root/
```

### 2. Run setup once
```bash
ssh root@<HEAD> 'bash /root/setup-cmsh-monitoring.sh --interval 60'
```

### 3. Verify
```bash
cmsh -c "monitoring; list"
cmsh -c "device; use node001; monitoring; get process-metrics"
cmsh -c "device; foreach -c (monitoring; get process-metrics)"
```

### 4. Import Grafana dashboard
```bash
# Import scripts/bcm-process-metrics-dashboard.json into Grafana
# Prometheus scrapes from: /var/lib/prometheus/node-exporter/bcm_process_metrics.prom
```

---

## Grafana Dashboard (15 panels)

| Panel | What |
|---|---|
| CPU Contention Score | Gauge: 0=idle, ≥0.9=RED |
| Service Core Pie | Weka vs Slurm vs NVIDIA vs system |
| Weka Core Usage | Gauge with 17-core threshold |
| Weka Core Alert | 0/1 stat — goes RED if exceeded |
| Node Core Count | Total cores per node |
| Process Count | Count by service class |
| Service Usage Over Time | Stacked timeseries |
| Weka Core History | Trend + limit line |
| Per-Core CPU | All cores individually |
| Top Processes by CPU | Top 15, filterable |
| Top by Core Count | Cores consumed per process |
| RSS Memory | Memory hogs |
| Thread Count | Thread tracking |
| Slurm vs Weka | Direct contention comparison |
| Contention History | Score trend over time |

---

## Service Classification Reference

| Service Label | Processes Matched |
|---|---|
| `weka` | weka*, WekaIO* |
| `slurm` | slurm*, srun, slurmstepd, sbatch |
| `nvidia` | nvsm*, nvidia*, dcgm*, nv-* |
| `bcm` | cmd, cmsh, cmjob, cmguiservlet |
| `mysql` | mysqld, mariadbd |
| `dhcp` | dhcpd |
| `tftp` | atftpd, in.tftpd, tftpd |
| `nfs` | nfsd, rpc.mountd, rpcbind, rpc.statd |
| `cron` | cron, crond, atd |
| `database` | mongod, postgres, redis* |
| `system` | ssh*, rsyslog*, systemd*, journald |
| `kernel` | kworker/*, cpuhp/*, rcu_*, ksoftirqd, kswapd, idle_inject/*, etc |
| `app` | python*, java, node |
| *(actual name)* | Everything else uses its real process name |

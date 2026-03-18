---
title: "MLX5 Syslog Flood Workaround — ACCESS_REG(0x805)"
subtitle: "Issue Summary, NVIDIA Fix Timeline, and RSyslog Workaround"
author: "BCM Infrastructure Team"
date: "March 12, 2026"
---

# MLX5 Syslog Flood Workaround

## 1. Executive Summary

All DGX compute nodes are producing **high-frequency kernel error messages** from the Mellanox ConnectX (mlx5) driver approximately **every 30 seconds**. These messages flood `/var/log/syslog` and `dmesg`, consuming disk space and making log analysis difficult.

| Item | Detail |
|------|--------|
| **Severity** | Medium — no functional impact to workloads |
| **Affected** | All DGX nodes (GPU and CPU) |
| **Root Cause** | mlx5 driver `ACCESS_REG(0x805)` register bug |
| **Permanent Fix** | DGX OS 7.4.0 (NVIDIA confirmed) |
| **Interim Workaround** | RSyslog filter (NVIDIA recommended) |
| **Deployment Method** | Ansible from BCM head node |

---

## 2. Issue Details

### Error Messages

The following kernel messages repeat every ~30 seconds on **every node**:

```
kernel: mlx5_core 0000:05:00.0: mlx5_cmd_out_err:839:(pid XXXXX):
  ACCESS_REG(0x805) op_mod(0x1) failed, status bad operation(0x2),
  syndrome (0x9a6171), err(-22)

kernel: mlx5_cmd_out_err: 16 callbacks suppressed
```

### Impact

- **Disk Space**: Syslog and dmesg logs grow rapidly, consuming storage
- **Log Noise**: Legitimate errors are buried in the noise
- **Monitoring**: Syslog-based alerting may trigger false positives
- **No Functional Impact**: The errors do not affect network performance, NCCL, or workload execution

### Observed On

- All DGX nodes across all availability zones
- First observed: March 5, 2026
- NVIDIA Support case opened and confirmed

---

## 3. Root Cause Analysis

The mlx5 (Mellanox ConnectX) network driver attempts to access hardware register `0x805` (`ACCESS_REG` command) repeatedly. This register access fails with:

- **Status**: `bad operation (0x2)`
- **Syndrome**: `0x9a6171`
- **Error code**: `-22` (`EINVAL` — invalid argument)

This is a **known driver bug** where the driver queries a register that is not supported in the current firmware/driver combination. The operation is harmless but generates kernel log entries on each retry.

---

## 4. Permanent Fix — DGX OS 7.4.0

NVIDIA has confirmed that this issue is **resolved in DGX OS version 7.4.0**.

- **Reference**: [NVIDIA DGX OS 7 Resolved Issues — access-reg-command-failure-with-err-22](https://docs.nvidia.com/dgx/dgx-os-7-user-guide/resolved-issues.html#access-reg-command-failure-with-err-22)
- **NVIDIA Support Statement** (March 9, 2026): *"As you rightly noted, this issue was resolved in DGX OS version 7.4.0."*

> **Note**: The OS upgrade path to 7.4.0 is not immediately available in our environment. The RSyslog workaround below provides an interim solution until the upgrade can be scheduled.

---

## 5. Recommended Workaround — RSyslog Filter

### What It Does

An RSyslog filter rule is deployed to each node that **silences** (drops) messages containing `ACCESS_REG(0x805)` before they reach `/var/log/syslog`. This is the exact workaround recommended by **NVIDIA Support** (engineer: Donghwan).

### Configuration File

**File**: `/etc/rsyslog.d/10-mlx5-filter.conf`

```
# MLX5 Kernel Noise Suppression (NVIDIA workaround)
# Issue: ACCESS_REG(0x805) op_mod(0x1) failed, err(-22)
# Fix: DGX OS 7.4.0
:msg, contains, "ACCESS_REG(0x805)" stop
:msg, contains, "mlx5_cmd_out_err" stop
```

### How RSyslog Filtering Works

```
Linux Kernel (printk)
        │
        ▼
systemd-journald (collects kernel messages)
        │
        ▼ (imjournal module)
rsyslogd
  ├─ Reads from journald via imjournal
  ├─ Applies filter rules from /etc/rsyslog.d/*.conf
  │   └─ 10-mlx5-filter.conf: DROP if msg contains "ACCESS_REG(0x805)"
  └─ Writes remaining messages to /var/log/syslog
```

Messages matching the filter are **stopped** before reaching any output action (file, remote, etc.).

### Alternative: Route to Separate File

If an audit trail is preferred over complete suppression, messages can be redirected to a separate file instead of dropped:

```
:msg, contains, "ACCESS_REG(0x805)" /var/log/kernel-noise.log
:msg, contains, "ACCESS_REG(0x805)" stop
```

This saves matching messages to `/var/log/kernel-noise.log` (with logrotate) while still keeping them out of `/var/log/syslog`.

---

## 6. Deployment Method — Ansible from BCM Head Node

### With Customer Consent

If approved, we will deploy the RSyslog filter via Ansible from the BCM head node:

```bash
# Deploy to all compute nodes
ansible-playbook -i inventories/<environment>/hosts.yml \
    playbooks/rsyslog-silence.yml

# Optional: dry-run first (no changes made)
ansible-playbook -i inventories/<environment>/hosts.yml \
    playbooks/rsyslog-silence.yml --check --diff
```

### What the Playbook Does

1. **Verifies** RSyslog is installed on each target node
2. **Backs up** existing RSyslog configuration
3. **Deploys** the filter file to `/etc/rsyslog.d/10-mlx5-filter.conf`
4. **Validates** the new config with `rsyslogd -N1`
5. **Restarts** the RSyslog service
6. **Tests** that messages are suppressed (via `logger` injection)

### CMSS Persistence (Survive Reimaging)

For nodes that may be reimaged, a BCM Configuration Overlay ensures the filter is automatically re-applied:

```bash
# Create CMSS overlay (run once on head node)
ansible-playbook -i inventories/<environment>/hosts.yml \
    playbooks/cmss-rsyslog-overlay.yml
```

---

## 7. Validation

After deployment, verification can be performed on any target node:

```bash
# 1. Check filter is deployed
cat /etc/rsyslog.d/10-mlx5-filter.conf

# 2. Check RSyslog is running
systemctl status rsyslog

# 3. Validate RSyslog config
sudo rsyslogd -N1

# 4. Test suppression via user-space logger
logger -p kern.info -t kernel "ACCESS_REG(0x805) TEST"
# Should NOT appear in: tail -f /var/log/syslog | grep ACCESS_REG

# 5. Test suppression via kernel message buffer
echo 'ACCESS_REG(0x805) TEST from /dev/kmsg' | sudo tee /dev/kmsg >/dev/null
# Should NOT appear in: tail -f /var/log/syslog | grep ACCESS_REG
```

---

## 8. Rollback Procedure

To remove the workaround (e.g., after upgrading to DGX OS 7.4.0):

```bash
# Via Ansible (recommended)
ansible-playbook -i inventories/<environment>/hosts.yml \
    playbooks/rsyslog-silence.yml --tags rollback

# Manual (per node)
sudo rm /etc/rsyslog.d/10-mlx5-filter.conf
sudo systemctl restart rsyslog
```

---

## Appendix: NVIDIA Support References

- **NVIDIA Support Case**: Noisy mlx5 kernel logs — `ACCESS_REG(0x805)` error
- **NVIDIA Engineer**: Donghwan (March 9, 2026)
- **NVIDIA Guidance**: Create `/etc/rsyslog.d/10-mlx5-filter.conf` with content `:msg, contains, "ACCESS_REG(0x805)" stop`, then `systemctl restart rsyslog`
- **DGX OS 7.4.0 Release Notes**: [Resolved Issues — access-reg-command-failure-with-err-22](https://docs.nvidia.com/dgx/dgx-os-7-user-guide/resolved-issues.html#access-reg-command-failure-with-err-22)

# BCM 11.0 Installation & Troubleshooting Guide

> **Based on real deployment experience** — every issue below was encountered and resolved
> during BCM 11.0 lab setup with KVM-based head node and stateless compute nodes.

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                    KVM Host                          │
│                                                      │
│   ┌──────────┐     ┌──────────┐    ┌──────────┐    │
│   │ bcm-head │     │ cpu-n01  │    │ gpu-n01  │    │
│   │ (BCM 11) │     │ stateless│    │ stateless│    │
│   └────┬─────┘     └────┬─────┘    └────┬─────┘    │
│        │                 │               │           │
│   ─────┴─────────────────┴───────────────┴───────   │
│              bcm-mgmt bridge (L2)                    │
│              192.168.200.0/24                        │
└─────────────────────────────────────────────────────┘
```

| Component | Role | IP |
|---|---|---|
| `bcm-head` | BCM head node, DHCP, TFTP, NFS, Slurm controller | `192.168.200.254` |
| `cpu-n01` | Stateless compute (PXE boot) | `192.168.200.1` |
| `cpu-n02` | Stateless compute (PXE boot) | `192.168.200.2` |
| `gpu-n01` | GPU compute (PXE boot) | `192.168.200.3` |

**Key fact**: BCM compute nodes are **stateless** — they PXE boot every time, download kernel+initramfs via TFTP, and mount root filesystem via NFS from the head node. There is no OS on the local disk.

---

## 2. Initial Setup Checklist

### 2.1 Head Node VM Configuration

```bash
# Head node needs TWO network interfaces:
# 1. External (default bridge) — for SSH access from host
# 2. Internal (bcm-mgmt bridge) — for compute node management

# Verify head node has both interfaces
sudo virsh domiflist bcm-head
# Expected:
#  vnet1  network  default    virtio  52:54:00:xx:xx:xx   (external)
#  vnet2  network  bcm-mgmt   virtio  52:54:00:xx:xx:xx   (internal — enp2s0)
```

### 2.2 Compute Node VM Configuration

```bash
# Compute nodes need:
# 1. Boot order: network FIRST, then hd
# 2. Connected to bcm-mgmt bridge (same L2 as head node enp2s0)

sudo virsh dumpxml cpu-n01 | grep -A3 "<os>"
# Must show: <boot dev='network'/> BEFORE <boot dev='hd'/>

sudo virsh domiflist cpu-n01
# Must show: bcm-mgmt network
```

### 2.3 IP Address on Internal Interface

```bash
# On bcm-head, verify 192.168.200.254 is on the internal interface (enp2s0)
ssh root@<bcm-head-external-ip> "ip -4 addr show enp2s0"

# If missing, add it:
ssh root@<bcm-head-external-ip> "ip addr add 192.168.200.254/24 dev enp2s0"
```

---

## 3. Problem #1: `cmd` Daemon Resets `iptables` to DROP

### Symptoms
- SSH to bcm-head intermittently fails
- `iptables -L INPUT` shows `DROP` policy
- Services work after manual `iptables -P INPUT ACCEPT` but revert within minutes
- DHCP and TFTP unreachable from compute nodes

### Root Cause
BCM's `cmd` daemon (cluster management daemon) aggressively manages `iptables` rules. It periodically resets the firewall policy to `DROP` and adds its own rules, overriding any manual changes.

### Fix — Disable BCM Firewall Management (Permanent)

```bash
# Via SSH (if accessible) or via VNC console:

# Step 1: Flush current rules to regain access
iptables -P INPUT ACCEPT
iptables -P OUTPUT ACCEPT
iptables -P FORWARD ACCEPT
iptables -F

# Step 2: Permanently disable BCM's firewall management
cmsh
# In cmsh shell:
base
set FirewallEnabled no
commit
quit

# Step 3: Verify
iptables -L INPUT -n | head -1
# Expected: Chain INPUT (policy ACCEPT)
```

> **IMPORTANT**: If SSH is blocked and you can't connect, use the VNC console
> (`virsh vncdisplay bcm-head` to get the VNC port).

### Verification
```bash
# This should stay ACCEPT even after 5+ minutes:
watch -n 30 "iptables -L INPUT -n | head -1"
```

---

## 4. Problem #2: DHCP Listening on Wrong Interface

### Symptoms
- Compute nodes PXE boot but never get DHCP response
- `tcpdump -i enp2s0 udp port 67` shows zero packets
- `tcpdump -i any udp port 67` also shows zero packets
- `journalctl -u dhcpd` shows no DISCOVER/OFFER/ACK entries

### Root Cause
The `cmd` daemon writes `/etc/sysconfig/dhcpd` with:
```
DHCPDARGS="enp1s0"
```
This binds DHCP to `enp1s0` (external interface), NOT `enp2s0` (internal/bcm-mgmt where compute nodes are).

Even if you manually fix it with `sed`, `cmd` will **overwrite it back** on the next cycle.

### Fix — Start DHCP Manually on the Correct Interface

```bash
# Step 1: Stop the systemd-managed dhcpd (cmd controls it)
systemctl stop dhcpd

# Step 2: Kill any leftover dhcpd processes
killall dhcpd 2>/dev/null

# Step 3: Start dhcpd manually on the correct interface
# Note: config file is at /etc/dhcpd.conf (NOT /etc/dhcp/dhcpd.conf)
/usr/sbin/dhcpd -cf /etc/dhcpd.conf --no-pid enp2s0

# Step 4: Verify
pgrep dhcpd && echo "DHCPD RUNNING"
ss -uln | grep ":67 "
# Expected: Listening on UDP:67
```

> **WARNING**: Do NOT use the `-f` (foreground) flag or your SSH session will hang.

### Verification
```bash
# After starting compute VMs, you should see DHCP activity:
journalctl --no-pager | grep -iE "DHCPACK|DISCOVER" | tail -5
# Expected:
# DHCPDISCOVER from 52:54:00:xx:xx:xx via enp2s0
# DHCPOFFER on 192.168.200.1 to 52:54:00:xx:xx:xx via enp2s0
# DHCPREQUEST for 192.168.200.1 from 52:54:00:xx:xx:xx via enp2s0
# DHCPACK on 192.168.200.1 to 52:54:00:xx:xx:xx via enp2s0
```

---

## 5. Problem #3: TFTP Not Running or Unreachable

### Symptoms
- VNC console shows iPXE: `TFTP connection timeout` at `lpxelinux.0`
- Node gets DHCP IP but cannot download boot files

### Root Cause
TFTP may not be running, or may not be running as root (needed to read `/tftpboot`), or the `cmd` daemon may have stopped it.

### Fix — Start TFTP Manually

```bash
# Step 1: Kill any existing TFTP
killall in.tftpd 2>/dev/null
systemctl stop tftpd.service tftpd.socket 2>/dev/null

# Step 2: Start as root with high thread count
/usr/sbin/in.tftpd --daemon --user root --maxthread=100 /tftpboot

# Step 3: Verify
pgrep in.tftpd && echo "TFTP RUNNING"
ss -uln | grep ":69 "
# Expected: Listening on UDP:69

# Step 4: Test locally
cd /tmp
atftp -g -r x86_64/bios/lpxelinux.0 -l test.0 192.168.200.254
ls -la test.0
# Expected: ~91KB file
```

### Boot File Verification
```bash
# These files must exist:
ls -la /tftpboot/x86_64/bios/lpxelinux.0
# Expected: ~91KB

# DHCP config must point to this file:
grep "filename" /etc/dhcpd.conf
```

---

## 6. Problem #4: Nodes Boot from Disk Instead of Network

### Symptoms
- Compute node VMs show "No bootable device" or boot into GRUB
- Node never sends DHCP DISCOVER

### Root Cause
VM boot order has `hd` before `network`, or `network` boot was removed.

### Fix — Set Network Boot First

```bash
# Check current boot order
sudo virsh dumpxml cpu-n01 | grep "boot dev"

# If network is missing or hd is first:
sudo virt-xml cpu-n01 --edit --boot network,hd
# OR edit XML directly:
sudo virsh edit cpu-n01
# Change <os> section to:
#   <boot dev='network'/>
#   <boot dev='hd'/>

# Restart the VM
sudo virsh destroy cpu-n01
sudo virsh start cpu-n01
```

> **Remember**: BCM compute nodes are **stateless** — there is no OS on disk.
> They MUST PXE boot every time. Setting boot to `hd` only will always fail.

---

## 7. Problem #5: NFS Root Mount Fails

### Symptoms
- Node gets DHCP, downloads kernel via TFTP, but hangs during boot
- Kernel panic: "Unable to mount root fs"

### Diagnosis
```bash
# On head node, check NFS exports:
exportfs -v
# Must include:
# /cm/node-installer  192.168.200.0/24(ro,no_root_squash)

showmount -e localhost
# Must show /cm/node-installer, /cm/shared, /home

# Check NFS service
systemctl status nfs-server
```

### Fix
```bash
# If NFS exports are missing:
exportfs -r   # re-export all

# If NFS service is down:
systemctl start nfs-server
systemctl enable nfs-server

# Verify from compute node perspective (on head node):
mount -t nfs 192.168.200.254:/cm/node-installer /mnt -o ro
ls /mnt/
# Should show root filesystem contents
umount /mnt
```

---

## 8. Complete Service Startup Sequence

After every reboot of bcm-head, run this checklist:

```bash
# === 1. Fix Firewall ===
iptables -P INPUT ACCEPT
iptables -P OUTPUT ACCEPT
iptables -P FORWARD ACCEPT
iptables -F
cmsh -c "base; set FirewallEnabled no; commit"

# === 2. Fix IP ===
ip addr add 192.168.200.254/24 dev enp2s0 2>/dev/null

# === 3. Start DHCP on correct interface ===
systemctl stop dhcpd
killall dhcpd 2>/dev/null
sleep 1
/usr/sbin/dhcpd -cf /etc/dhcpd.conf --no-pid enp2s0

# === 4. Start TFTP ===
killall in.tftpd 2>/dev/null
/usr/sbin/in.tftpd --daemon --user root --maxthread=100 /tftpboot

# === 5. Verify NFS ===
exportfs -v | grep node-installer
systemctl is-active nfs-server

# === 6. Verify all services ===
echo "FW:   $(iptables -L INPUT -n | head -1)"
echo "IP:   $(ip -4 addr show enp2s0 | grep 254)"
echo "DHCP: $(pgrep dhcpd && echo OK || echo FAIL)"
echo "TFTP: $(pgrep in.tftpd && echo OK || echo FAIL)"
echo "NFS:  $(systemctl is-active nfs-server)"
echo "CMD:  $(systemctl is-active cmd)"
```

---

## 9. Node Provisioning Verification

After starting compute VMs, monitor provisioning:

```bash
# Watch DHCP leases (should see DISCOVER → OFFER → REQUEST → ACK)
journalctl -f | grep -iE "dhcp"

# Watch node status in BCM
watch -n 10 'cmsh -c "device list"'
# States: DOWN → INSTALLING → UP

# Ping test
ping -c1 192.168.200.1   # node001
ping -c1 192.168.200.2   # node002

# SSH to compute node (once UP)
ssh root@192.168.200.1

# Slurm status
sinfo
# Expected: nodes in "idle" state once provisioned
```

---

## 10. Quick Diagnostic Commands

| Check | Command |
|---|---|
| Firewall policy | `iptables -L INPUT -n \| head -1` |
| DHCP running? | `pgrep dhcpd && echo YES` |
| DHCP interface | `cat /etc/sysconfig/dhcpd` |
| TFTP running? | `pgrep in.tftpd && echo YES` |
| TFTP test | `atftp -g -r x86_64/bios/lpxelinux.0 -l /tmp/test.0 192.168.200.254` |
| NFS exports | `exportfs -v` |
| Node status | `cmsh -c "device list"` |
| Node boot file | `ls -la /tftpboot/x86_64/bios/lpxelinux.0` |
| DHCP logs | `journalctl \| grep -i dhcp \| tail -10` |
| Slurm nodes | `sinfo` |
| Internal IP | `ip -4 addr show enp2s0` |
| VM boot order | `sudo virsh dumpxml <vm> \| grep "boot dev"` |

---

## 11. Lessons Learned

1. **`cmd` daemon is aggressive** — it manages iptables AND dhcpd config. Always disable its firewall management via `cmsh base; set FirewallEnabled no; commit`.

2. **DHCP interface matters** — `cmd` forces DHCP to `enp1s0` (external). You must manually start dhcpd on `enp2s0` (internal) after every reboot.

3. **Stateless nodes need PXE** — there is no OS on disk. Boot order must always be `network` first. Don't waste time trying to boot from disk.

4. **TFTP config file path** — BCM uses `/etc/dhcpd.conf`, NOT `/etc/dhcp/dhcpd.conf`. The `-cf` flag matters.

5. **VNC is your lifeline** — when SSH is blocked by firewall, use `virsh vncdisplay bcm-head` and connect via VNC to fix iptables.

6. **Test services individually** — verify each: firewall → IP → DHCP → TFTP → NFS → then try PXE boot.

7. **`cmsh` context matters** — run individual commands like `cmsh -c "device list"` or enter interactive mode and navigate: `base` → `set` → `commit`.

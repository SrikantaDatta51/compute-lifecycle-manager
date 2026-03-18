# SOP-301: NFS Deep Debug & Head Node Recovery — Emergency Runbook

> **Scope**: `/cm/shared` filesystem corruption causing cluster-wide Slurm outage.
> **Severity**: P1 — All job submissions blocked.
> **Audience**: Platform / SRE Engineers with root access to BCM head node.
> **Last Updated**: 2026-03-18

---

## Concepts: Understanding the Storage Stack Before You Debug

> [!TIP]
> **Read this section to understand WHY each debug command works.** Every command
> in this runbook targets a specific layer of the Linux storage stack. If you
> understand the layers, you'll know exactly where to look when something breaks.

### The Linux Storage Stack (Bottom → Top)

```
┌──────────────────────────────────────────────────────────────────────────┐
│  LAYER 7: APPLICATION                                                    │
│  sbatch, srun, sinfo, slurmd, slurmctld                                 │
│  → These read config files from /cm/shared                               │
│  → Debug: "What error does the application report?"                      │
│    Commands: sbatch --test-only, scontrol ping, systemctl status slurmd   │
├──────────────────────────────────────────────────────────────────────────┤
│  LAYER 6: NFS CLIENT (on compute nodes)                                  │
│  The network filesystem the nodes use to access /cm/shared               │
│  → mount -t nfs headnode:/cm/shared /cm/shared                           │
│  → Debug: "Can the node reach the NFS server and read files?"            │
│    Commands: mount | grep cm, stat /cm/shared, nfsstat -c                │
├──────────────────────────────────────────────────────────────────────────┤
│  LAYER 5: NFS SERVER (on head node)                                      │
│  The daemon that shares /cm/shared over the network                      │
│  → nfsd kernel threads + rpc.mountd + rpcbind                            │
│  → Debug: "Is the head node exporting /cm/shared?"                       │
│    Commands: exportfs -v, rpcinfo -p, ss -tlnp | grep 2049              │
├──────────────────────────────────────────────────────────────────────────┤
│  LAYER 4: VFS (Virtual File System)                                      │
│  Linux's abstraction layer — translates "read /cm/shared/file"           │
│  into the correct filesystem driver call (XFS, EXT4, etc.)               │
│  → Debug: "Can the kernel access the mount point?"                       │
│    Commands: ls /cm/shared, cat /cm/shared/file, mount | grep cm         │
├──────────────────────────────────────────────────────────────────────────┤
│  LAYER 3: FILESYSTEM (XFS or EXT4)                                       │
│  The on-disk data structures (superblock, inodes, journal)               │
│  → This lives INSIDE the loop image (or on a raw partition)              │
│  → Debug: "Is the filesystem metadata intact?"                           │
│    Commands: xfs_info, xfs_repair -n, e2fsck -n, dmesg | grep xfs       │
├──────────────────────────────────────────────────────────────────────────┤
│  LAYER 2: LOOP DEVICE (/dev/loop0) ◄── YOUR SETUP                       │
│  A virtual block device that reads/writes to a FILE instead              │
│  of a physical disk. Makes a file look like a disk partition.            │
│  → Debug: "Is the loop device attached to the correct image?"            │
│    Commands: losetup -a, losetup /dev/loop0, blkid /dev/loop0            │
├──────────────────────────────────────────────────────────────────────────┤
│  LAYER 1: BACKING IMAGE FILE                                             │
│  A large file (e.g., shared.img) sitting on the root filesystem          │
│  → Contains the entire /cm/shared filesystem as a binary blob            │
│  → Debug: "Is the image file intact on disk?"                            │
│    Commands: ls -lh <backing_file>, file <backing_file>, md5sum          │
├──────────────────────────────────────────────────────────────────────────┤
│  LAYER 0: PHYSICAL DISK (/dev/sda)                                       │
│  The actual hardware — spinning disk or SSD                              │
│  → If this fails, everything above it fails                              │
│  → Debug: "Is the hardware healthy?"                                     │
│    Commands: smartctl -a /dev/sda, dmesg | grep "medium error"           │
└──────────────────────────────────────────────────────────────────────────┘
```

**Key insight**: When you see `Input/output error` on `/cm/shared`, the error could originate at **any** layer from 0–3. You debug by starting at the top and working down until you find the broken layer.

---

### What is a Loop Device?

A **loop device** (`/dev/loop0`, `/dev/loop1`, etc.) is a Linux kernel feature that makes a **regular file** behave like a **block device** (like a disk partition).

```
Normal disk:     /dev/sda1  →  mount  →  /mnt/data
Loop device:     file.img   →  /dev/loop0  →  mount  →  /cm/shared
```

**Why does BCM use this?**
- BCM creates a large image file (e.g., 100GB) on the head node's root filesystem
- It loop-mounts this file as `/cm/shared`
- Inside this image is a full XFS or EXT4 filesystem
- This lets BCM manage `/cm/shared` as a single portable file — it can be backed up, moved, or resized easily

**Key commands for loop devices:**

| Command | What it does | When to use |
|---------|-------------|-------------|
| `losetup -a` | List ALL loop devices and their backing files | First thing — find what backs `/dev/loop0` |
| `losetup /dev/loop0` | Show details for a specific loop device | See the backing file path, offset, flags |
| `losetup -l` | Extended list format with columns | More readable output |
| `losetup -d /dev/loop0` | **Detach** loop device (unsafe if mounted!) | Only after unmounting `/cm/shared` |
| `losetup /dev/loop0 file.img` | **Attach** backing file to loop device | Re-attach after detach, or after reboot |
| `losetup -c /dev/loop0` | Reload the loop device's size from backing file | After resizing the backing image |
| `blkid /dev/loop0` | Show filesystem type inside the loop image | Determine if it's XFS or EXT4 |

---

### What is NFS?

**NFS (Network File System)** allows computers to access files over a network as if they were local. In BCM:

```
HEAD NODE (NFS Server)                    COMPUTE NODE (NFS Client)
┌─────────────────────┐                  ┌─────────────────────────┐
│ /cm/shared (local)  │  ── network ──►  │ /cm/shared (NFS mount)  │
│  ↑                  │     port 2049    │  ↑                      │
│  mounted from       │                  │  mounted from            │
│  /dev/loop0         │                  │  headnode:/cm/shared     │
└─────────────────────┘                  └─────────────────────────┘
```

**NFS has two sides that can fail independently:**

| Component | Where | What it does | How it breaks |
|-----------|-------|-------------|---------------|
| **NFS Server** (`nfsd`) | Head node | Serves files to network | Crashes, runs out of threads, module unloaded |
| **RPC Bind** (`rpcbind`) | Head node | Maps NFS services to ports | If down, clients can't find NFS server |
| **Export Table** (`/etc/exports`) | Head node | Defines WHICH dirs are shared | Missing entry = clients get "access denied" |
| **NFS Client** | Compute node | Mounts remote dir locally | Stale handle, timeout, wrong mount options |

**Critical mount options:**

| Option | Meaning | Impact |
|--------|---------|--------|
| `hard` (default) | Retry NFS requests forever until server responds | **Processes hang in D-state** — can't kill with `kill -9` |
| `soft` | Return error (EIO) after timeout | You get `Input/output error` — **your SPANK error!** |
| `intr` | Allow signals to interrupt hung NFS | Lets you Ctrl+C hung commands (deprecated in NFSv4) |
| `no_root_squash` | Root on client = root on server | Required for Slurm/munge to read files as root |
| `sync` | Server confirms writes hit disk | Slower but safer — prevents data loss |

---

### What is a Filesystem? (XFS / EXT4)

A filesystem is the **data structure** that organizes bytes on disk (or in an image) into files and directories. Think of it like a book's index — without it, you have pages of text but no way to find anything.

**Key filesystem structures:**

| Structure | What it is | If corrupted... |
|-----------|-----------|-----------------|
| **Superblock** | Master record: filesystem size, type, features, where to find everything else | Filesystem won't mount at all |
| **Inode** | Metadata for one file: size, permissions, timestamps, pointers to data blocks | File becomes inaccessible |
| **Journal (Log)** | Record of in-flight writes (for crash recovery) | XFS shuts down; EXT4 remounts read-only |
| **Directory entries** | Map filenames → inode numbers | `ls` fails, files "disappear" |
| **Data blocks** | Actual file contents | Files contain garbage or are truncated |

**XFS vs EXT4 — how they handle errors:**

| Behavior | XFS | EXT4 |
|----------|-----|------|
| On corruption detected | **Shuts down filesystem entirely** (no more I/O) | Remounts read-only (reads OK, writes fail) |
| Journal replay | Must unmount first, then `xfs_repair` | Auto-replays on mount |
| Repair tool | `xfs_repair` (cannot run on mounted FS) | `e2fsck` (cannot run on mounted FS) |
| Aggressive repair | `xfs_repair -L` (zeros journal — data loss) | `e2fsck -fy` (auto-answer yes) |
| Superblock backup | No backup superblock | Has backup superblocks (use `e2fsck -b`) |

**Why XFS "shutdown" is so disruptive:**
When XFS detects an inconsistency, it **immediately shuts down** — no reads, no writes, nothing. This is a safety feature to prevent further damage. But it means `/cm/shared` becomes instantly inaccessible, which kills NFS, which kills Slurm on every node.

---

### BCM Storage Architecture — Putting It Together

```
┌─────────────────── HEAD NODE ──────────────────────────────────────┐
│                                                                     │
│  /dev/sda (physical disk)                                          │
│    └── /dev/sda1 (partition, XFS or EXT4)                          │
│          └── / (root filesystem)                                    │
│                └── /cm/.internal/shared.img  (large image file)     │
│                      │                                              │
│                      ▼                                              │
│                 losetup /dev/loop0 ←── kernel loop driver           │
│                      │                                              │
│                      ▼                                              │
│                 /cm/shared (mounted filesystem inside image)         │
│                   ├── apps/slurm/etc/slurm/slurm.conf              │
│                   ├── apps/slurm/etc/slurm/plugstack.conf ◄─ ERROR │
│                   ├── apps/slurm/current/bin/ (binaries)           │
│                   └── apps/munge/ (auth)                           │
│                      │                                              │
│                      ▼                                              │
│                 NFS export (nfsd, port 2049)                        │
│                                                                     │
└─────────┬───────────────────────────────────────────────────────────┘
          │  Network
          ▼
┌─────────────────── COMPUTE NODE ───────────────────────────────────┐
│                                                                     │
│  mount -t nfs headnode:/cm/shared /cm/shared                       │
│    └── NFS client ──► /cm/shared (remote mount)                    │
│          └── slurmd reads slurm.conf, plugstack.conf               │
│          └── sbatch reads plugstack.conf to load SPANK plugins     │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**The chain of failure for your SPANK error:**

```
1. Something corrupts the XFS filesystem inside /dev/loop0
   (could be: disk error, power loss, full disk, kernel bug)
         │
         ▼
2. XFS detects corruption → SHUTS DOWN the filesystem
   (dmesg: "XFS: Filesystem has been shut down")
         │
         ▼
3. All reads from /cm/shared on head node return I/O error
   (NFS server can't read the files it's supposed to serve)
         │
         ▼
4. NFS server returns errors to compute nodes
   (or: NFS clients see stale handle / EIO)
         │
         ▼
5. sbatch on compute node tries to read plugstack.conf via NFS
   → "Input/output error"
   → "SPANK: Failed to open plugstack.conf"
   → "Error: initialization failed"
         │
         ▼
6. ALL job submissions fail cluster-wide
```

---

### How Each Debug Command Maps to a Layer

| Command | Layer | What you're checking |
|---------|-------|---------------------|
| `sbatch --test-only ...` | 7 (App) | Can Slurm submit jobs? |
| `cat /cm/shared/apps/slurm/etc/slurm/plugstack.conf` | 6 (NFS/VFS) | Can you read the file at all? |
| `exportfs -v` | 5 (NFS Server) | Is `/cm/shared` being exported? |
| `mount \| grep cm` | 4 (VFS) | Is `/cm/shared` mounted? Read-only? |
| `dmesg \| grep xfs` | 3 (Filesystem) | Has XFS detected errors/shut down? |
| `losetup -a` | 2 (Loop) | Is `/dev/loop0` attached to the image? |
| `ls -lh /cm/.internal/shared.img` | 1 (Image) | Does the backing file exist? |
| `smartctl -H /dev/sda` | 0 (Hardware) | Is the physical disk healthy? |

**Debug strategy**: Run these 8 commands top-to-bottom. The first one that fails tells you which layer is broken. Then go to the corresponding section in this runbook.

---

### Key Linux Concepts for This Debug

#### D-State Processes (Uninterruptible Sleep)
When a process tries to read from a broken NFS mount (with `hard` mount option), it enters **D-state** — uninterruptible sleep. This means:
- The process is waiting for I/O that will never complete
- `kill -9` does NOT work on D-state processes
- The only way to free them is to fix the underlying I/O (fix NFS) or reboot
- Check with: `ps aux | awk '$8 ~ /^D/'`

#### Stale File Handle
An NFS "stale file handle" means the server has a different view of the filesystem than the client's cached handle. Causes:
- NFS server was restarted
- `/cm/shared` was unmounted and remounted on the server
- The underlying loop device was detached and reattached
- Fix: `umount -l` on client, then re-mount

#### Lazy Unmount (`umount -l`)
A regular `umount` will fail if any process has files open on the mount. "Lazy" unmount (`-l`) detaches the filesystem from the namespace immediately but delays the actual unmount until all file handles are closed. This is essential when you need to unmount a broken NFS mount that has stuck processes.

#### Loop Device Persistence
Loop devices do NOT survive a reboot by default. BCM must re-create the loop attachment on every boot. This is typically done via:
- `/etc/fstab` with the `loop` mount option
- A systemd `.mount` unit
- BCM's own init scripts

---

### How Disk Full Kills XFS Inside a Loop Device (Your Scenario)

This is the **most common cause** of `/cm/shared` corruption on BCM head nodes and the most misunderstood. Here's exactly what happens:

```
┌─────────────────────────────────────────────────────────────────┐
│  ROOT CAUSE: /var (or /) fills up to 100%                      │
│                                                                 │
│  WHY IT MATTERS:                                                │
│  The loop image file (e.g., shared.img) lives ON the root      │
│  filesystem. Even though /cm/shared "looks" like a separate     │
│  filesystem, every write to /cm/shared actually writes to       │
│  the image file, which lives on /.                              │
│                                                                 │
│  When / is full:                                                │
│  ┌───────────────────────────────────────────────────────┐      │
│  │ XFS inside loop0 tries to write a block               │      │
│  │        ↓                                              │      │
│  │ Loop driver translates to: write to shared.img        │      │
│  │        ↓                                              │      │
│  │ Root FS says: "ENOSPC — no space left on device"      │      │
│  │        ↓                                              │      │
│  │ Loop driver returns I/O error to XFS                  │      │
│  │        ↓                                              │      │
│  │ XFS receives unexpected I/O error                     │      │
│  │        ↓                                              │      │
│  │ XFS SHUTS DOWN (safety: prevent metadata corruption)  │      │
│  │        ↓                                              │      │
│  │ /cm/shared → ALL I/O returns -EIO                     │      │
│  │        ↓                                              │      │
│  │ NFS server returns I/O error to all compute nodes     │      │
│  │        ↓                                              │      │
│  │ sbatch: "SPANK: plugstack.conf: Input/output error"   │      │
│  └───────────────────────────────────────────────────────┘      │
│                                                                 │
│  KEY INSIGHT:                                                   │
│  The XFS inside loop0 is NOT actually "corrupted" in the        │
│  traditional sense. It shut down because it couldn't write.     │
│  Once you free space on /, the loop image can write again,      │
│  and after xfs_repair, the filesystem recovers cleanly.         │
└─────────────────────────────────────────────────────────────────┘
```

**Why `/var` specifically?** Common `/var` space consumers on BCM head nodes:

| Path | What fills it | Typical size |
|------|--------------|-------------|
| `/var/log/slurm/` | Slurm controller + daemon logs | 1–50 GB if not rotated |
| `/var/lib/mysql/` | SlurmDBD accounting database | 5–100 GB over time |
| `/var/log/journal/` | Systemd journal (all system logs) | 1–8 GB |
| `/var/log/messages` or `/var/log/syslog` | System log (kernel, daemons) | 1–10 GB |
| `/var/spool/slurm/` | Slurm job spool files | 1–20 GB with many jobs |
| `/var/lib/docker/` | Container images + layers | 10–200 GB |
| `/var/crash/` | Kernel crash dumps | 1–64 GB per dump |
| `/var/lib/rpm/` | RPM database | Usually small but can grow |

---

## ⚡ 60-Second Assessment (Copy-Paste Block)

Run this **first** on the head node to understand what you're dealing with:

```bash
echo "===== FILESYSTEM STATE ====="
mount | grep -E "cm|shared"
df -hT /cm/shared 2>&1 || echo "/cm/shared: CANNOT ACCESS"

echo ""
echo "===== LOOP DEVICE CHECK (BCM default) ====="
losetup -a 2>/dev/null || echo "No loop devices"
# If you see: /dev/loop0: [xxxx]:yyyy (/path/to/image.img)
# Then /cm/shared is a LOOPBACK MOUNT — see Section 1.5
BACKING_FILE=$(losetup -a 2>/dev/null | grep loop0 | sed 's/.*(//' | sed 's/)//')
if [ -n "$BACKING_FILE" ]; then
    echo "LOOP0 BACKING FILE: $BACKING_FILE"
    ls -lh "$BACKING_FILE" 2>/dev/null || echo "BACKING FILE INACCESSIBLE!"
fi

echo ""
echo "===== KERNEL FILESYSTEM ERRORS ====="
dmesg -T | grep -iE "error|corrupt|EIO|readonly|xfs|ext4|I\/O|remount|shutdown|loop" | tail -30

echo ""
echo "===== NFS SERVER STATE ====="
systemctl is-active nfs-server 2>/dev/null || systemctl is-active nfs-kernel-server 2>/dev/null || echo "NFS SERVER: NOT RUNNING"
exportfs -v 2>/dev/null | grep cm || echo "NO /cm EXPORTS FOUND"

echo ""
echo "===== NFS STATS (retransmits = bad) ====="
nfsstat -s 2>/dev/null | grep -A5 "rpc" || echo "nfsstat unavailable"

echo ""
echo "===== DISK HARDWARE HEALTH ====="
for disk in /dev/sd?; do
    echo -n "$disk: "
    smartctl -H $disk 2>/dev/null | grep -i "result\|overall" || echo "SMART unavailable"
done

echo ""
echo "===== PROCESSES STUCK IN D-STATE (I/O wait) ====="
ps aux | awk '$8 ~ /^D/ {print $0}' | head -20

echo ""
echo "===== OPEN FILES ON /cm/shared ====="
lsof /cm/shared 2>/dev/null | wc -l || echo "lsof unavailable or /cm/shared hung"

echo ""
echo "===== LVM STATUS ====="
lvs 2>/dev/null || echo "No LVM"
pvs 2>/dev/null || echo "No PVs"

echo ""
echo "===== RAID STATUS ====="
cat /proc/mdstat 2>/dev/null || echo "No software RAID"

echo ""
echo "===== BACKING FILESYSTEM (where the loop image lives) ====="
if [ -n "$BACKING_FILE" ]; then
    PARENT_DIR=$(dirname "$BACKING_FILE")
    df -hT "$PARENT_DIR" 2>/dev/null
    echo "If THIS filesystem is corrupt/full, the loop image is affected!"
fi
```

---

## Decision Tree: What Type of Failure Is This?

```
First: What is the mount device?
│
├─ /dev/loop0 (or any /dev/loopN)
│   └─► BCM Loopback Image Mount → Go to Section 1.5 FIRST
│       (this is the most common BCM setup)
│
Then check df:
│
├─ /var or / is 100% full
│   └─► Disk Full caused XFS shutdown → Go to Section 1.6 FIRST
│       (most common BCM root cause!)
│
Then check dmesg:
│
├─ "XFS ... Filesystem has been shut down" or "log error"
│   └─► XFS Journal Corruption → Go to Section 2 (or 1.6 if disk was full)
│
├─ "EXT4-fs error" or "Remounting filesystem read-only"
│   └─► EXT4 Error → Go to Section 3
│
├─ "I/O error" on sd*/nvme* device
│   └─► Hardware Disk Failure → Go to Section 4
│
├─ "NFSD: ... stale" or nfsd errors
│   └─► NFS Server Daemon Issue → Go to Section 5
│
├─ No errors in dmesg but /cm/shared hangs
│   └─► NFS Export / Stale Handle → Go to Section 6
│
└─ Nothing obvious
    └─► Full Debug Walkthrough → Go to Section 7
```

---

## 1.5. BCM Loop Device Architecture — `/dev/loop0` Recovery

> [!NOTE]
> If `/var` or `/` is 100% full, go to **Section 1.6** first — that is likely your root cause.
> The loop device repair won't help if there's no disk space for it to write to.

> [!IMPORTANT]
> **Your confirmed setup**: `/dev/loop0` → `/cm/shared`.
> This means BCM stores `/cm/shared` as a **large image file** on another filesystem,
> mounted via the Linux loop device. This is **BCM's default behavior**.

### What is a Loop Mount?

```
┌─────────────────────────────────────────────────────────┐
│  Physical Disk (/dev/sda)                               │
│  └── Partition (/dev/sda1 or LVM)                       │
│      └── Root Filesystem (ext4/xfs at /)                │
│          └── Image File (e.g., /cm/.internal/shared.img)│
│              └── /dev/loop0 (loop device)                │
│                  └── /cm/shared (XFS or EXT4 inside)    │
│                      └── apps/slurm/etc/slurm/...       │
└─────────────────────────────────────────────────────────┘
```

**Two layers can fail:**
1. **The image file's internal filesystem** (the XFS/EXT4 inside the `.img` file)
2. **The parent filesystem** holding the image file (if `/dev/sda1` is corrupt, the `.img` file is damaged)

### Step 1: Find the Backing Image File

```bash
# Show all loop devices and their backing files
losetup -a
# Expected output like:
# /dev/loop0: [64769]:1234567 (/cm/.internal/shared.img)
# or
# /dev/loop0: [64769]:1234567 (/root/cm-shared.img)
# or
# /dev/loop0: [64769]:1234567 (/var/lib/cm/shared.img)

# Save the backing file path
BACKING_FILE=$(losetup /dev/loop0 | awk '{print $NF}' | tr -d '()')
echo "Backing file: $BACKING_FILE"

# Alternative: if losetup shows nothing useful
losetup -l          # List format with more detail
losetup -j ""       # Show all associations
cat /proc/mounts | grep loop0

# Check the backing file health
ls -lh "$BACKING_FILE"
file "$BACKING_FILE"
# Should show something like:
# /cm/.internal/shared.img: SGI XFS filesystem data
# or
# /cm/.internal/shared.img: Linux rev 1.0 ext4 filesystem data
```

### Step 2: Check the Parent Filesystem

```bash
# Where does the image file physically live?
BACKING_DIR=$(dirname "$BACKING_FILE")
df -hT "$BACKING_DIR"
# This shows the REAL physical disk/partition holding the image

# Is the PARENT filesystem healthy?
mount | grep -w $(df "$BACKING_DIR" --output=target | tail -1)
# Check if it's read-only (ro) — if so, parent FS is corrupt too

# Check parent filesystem errors
dmesg -T | grep -iE "$(df "$BACKING_DIR" --output=source | tail -1)" | tail -20

# Check disk space on the parent
df -h "$BACKING_DIR"
# If 100% full → the image file can't grow or write → causes I/O errors
```

### Step 3: Diagnose the Loop Image Filesystem

```bash
# What filesystem type is INSIDE the loop image?
blkid /dev/loop0
# Or:
file "$BACKING_FILE"
# Or:
mount | grep loop0

# Check for filesystem errors on the loop device
dmesg -T | grep -i loop0 | tail -20
dmesg -T | grep -iE "xfs.*loop|ext4.*loop|loop.*error" | tail -20
```

### Step 4: Repair the Loop Image

```bash
# ============================================================
# UNMOUNT /cm/shared FIRST (see Section 1 Emergency Stop)
# ============================================================

# Stop NFS exports and Slurm (same as Section 1)
exportfs -ua
systemctl stop slurmctld
pdsh -w node[001-064] "systemctl stop slurmd; umount -l /cm/shared" 2>/dev/null

# Unmount the loop device
umount /cm/shared
# If it hangs:
umount -l /cm/shared

# ============================================================
# OPTION A: Keep the loop device attached, repair /dev/loop0
# ============================================================
# Check if loop is still attached after umount:
losetup /dev/loop0

# FOR XFS (most common on BCM):
xfs_repair -n /dev/loop0 2>&1 | tee /tmp/loop_xfs_dryrun.log    # DRY RUN
xfs_repair /dev/loop0 2>&1 | tee /tmp/loop_xfs_repair.log       # ACTUAL REPAIR
# If dirty log:
xfs_repair -L /dev/loop0 2>&1 | tee /tmp/loop_xfs_repair_L.log  # ZERO LOG (data loss risk)

# FOR EXT4:
e2fsck -n /dev/loop0 2>&1 | tee /tmp/loop_e2fsck_dryrun.log     # DRY RUN
e2fsck -fy /dev/loop0 2>&1 | tee /tmp/loop_e2fsck.log           # AUTO-REPAIR

# ============================================================
# OPTION B: Detach loop, repair the image file directly
# ============================================================
# If /dev/loop0 is in a bad state, detach it:
losetup -d /dev/loop0

# Re-attach cleanly:
losetup /dev/loop0 "$BACKING_FILE"
# Verify:
losetup /dev/loop0

# Now repair:
xfs_repair /dev/loop0        # or e2fsck -fy /dev/loop0

# ============================================================
# OPTION C: If the PARENT filesystem is corrupt
# ============================================================
# The image file itself may be damaged because the parent FS is bad.
# You MUST fix the parent filesystem FIRST:

# 1. Detach the loop device
losetup -d /dev/loop0

# 2. Identify parent filesystem device
PARENT_DEV=$(df "$BACKING_DIR" --output=source | tail -1)
echo "Parent device: $PARENT_DEV"

# 3. Unmount and repair parent (DANGEROUS — may affect other services)
# umount $PARENT_DEV
# xfs_repair $PARENT_DEV   # or e2fsck -fy $PARENT_DEV
# mount $PARENT_DEV

# 4. Then check if image file is intact
file "$BACKING_FILE"
md5sum "$BACKING_FILE"    # For comparison if you have a known-good hash

# 5. Re-attach and repair the loop image
losetup /dev/loop0 "$BACKING_FILE"
xfs_repair /dev/loop0
```

### Step 5: Remount and Restore

```bash
# ============================================================
# After repair, remount /cm/shared
# ============================================================

# Ensure loop device is attached
losetup /dev/loop0 "$BACKING_FILE" 2>/dev/null
losetup /dev/loop0     # Verify

# Mount
mount /dev/loop0 /cm/shared
mount | grep loop0     # Verify: should show "rw" not "ro"

# Verify critical files
ls /cm/shared/apps/slurm/etc/slurm/plugstack.conf && echo "✓ plugstack.conf OK"
ls /cm/shared/apps/slurm/etc/slurm/slurm.conf && echo "✓ slurm.conf OK"
ls /cm/shared/apps/slurm/current/bin/sinfo && echo "✓ Slurm binaries OK"

# Re-export NFS
exportfs -a
exportfs -v | grep cm

# Remount on nodes
pdsh -w node[001-064] "mount /cm/shared" 2>&1 | dshbak -c
pdsh -w node[001-064] "cat /cm/shared/apps/slurm/etc/slurm/plugstack.conf > /dev/null && echo OK || echo FAIL" 2>&1 | dshbak -c

# Restart Slurm stack
systemctl start munge && systemctl start slurmdbd && sleep 5 && systemctl start slurmctld
pdsh -w node[001-064] "systemctl restart munge && systemctl restart slurmd"
scontrol update NodeName=ALL State=RESUME
sinfo -N -l
```

### Step 6: Make the Loop Mount Persistent

After recovery, ensure `/cm/shared` will survive a reboot:

```bash
# Check how BCM configures the loop mount at boot:
grep -r loop /etc/fstab
grep -r loop /etc/systemd/system/ 2>/dev/null
grep -r cm.shared /etc/systemd/system/ 2>/dev/null
systemctl list-units | grep -i cm

# BCM typically has a systemd unit or init script that:
#   1. losetup /dev/loop0 <backing_file>
#   2. mount /dev/loop0 /cm/shared
#
# If /etc/fstab has it:
grep loop /etc/fstab
# Expected line like:
# /cm/.internal/shared.img  /cm/shared  xfs  loop,defaults  0  0

# If NOT in fstab, check for BCM's own mount mechanism:
grep -r "cm.shared\|loop0" /etc/init.d/ 2>/dev/null
systemctl cat cm-shared.mount 2>/dev/null
```

### Loop Device Specific Failure Modes

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| `losetup -a` shows nothing | Loop device detached | `losetup /dev/loop0 <image_file>` then mount |
| `losetup` shows backing file but mount fails | Filesystem inside image corrupt | `xfs_repair /dev/loop0` or `e2fsck -fy /dev/loop0` |
| Backing image file returns I/O error | **Parent filesystem corrupt** | Repair parent FS first |
| Backing image file missing | File deleted or parent FS lost data | Restore from backup |
| `/cm/shared` mounted read-only | Kernel detected errors, auto-remounted RO | Unmount → repair → remount RW |
| Parent filesystem 100% full | Image can't write new blocks | Free space on parent FS |
| `loop0: detected capacity change` after reboot | Image file was resized or recreated | Reattach loop: `losetup -c /dev/loop0` |

---

## 1.6. `/var` or `/` Full — Root Cause Recovery (Confirmed Scenario)

> [!CAUTION]
> **`/var` at 100% is the most common root cause of `/cm/shared` failure on BCM.**
> If `/var` and `/` are on the same partition (which is typical), then the loop device
> backing file cannot write → XFS shuts down → NFS fails → Slurm dies.

### Why Disk Full Kills Everything

```
/var 100% full
   ↓
Same partition as /  ──→  / is also full
   ↓
Loop image file (shared.img) lives on /
   ↓
Writes to /dev/loop0 fail (ENOSPC)
   ↓
XFS inside loop0 receives I/O errors
   ↓
XFS SHUTS DOWN (cannot write journal)
   ↓
/cm/shared → all I/O returns EIO
   ↓
NFS returns I/O error to compute nodes
   ↓
SPANK plugstack.conf: Input/output error
   ↓
ALL job submissions fail cluster-wide
```

### Step 1: Confirm Disk Full is the Root Cause

```bash
# Check disk usage
df -h / /var /var/log /tmp
# If / or /var shows 100% (or Use% = 100%) → confirmed

# Are / and /var the same partition?
df / --output=source
df /var --output=source
# If same device → they share space

# Confirm the loop image lives on the full partition
BACKING_FILE=$(losetup /dev/loop0 2>/dev/null | awk '{print $NF}' | tr -d '()')
echo "Loop image: $BACKING_FILE"
df -h "$(dirname "$BACKING_FILE")"    # Is THIS filesystem full?

# Check dmesg for the ENOSPC chain
dmesg -T | grep -iE "No space|ENOSPC|xfs.*shut|loop.*error" | tail -20
```

### Step 2: Emergency Cleanup — Free Space NOW

```bash
# ============================================================
# FIND THE BIGGEST SPACE CONSUMERS
# ============================================================
du -sh /var/*/ 2>/dev/null | sort -rh | head -15
du -sh /var/log/*  2>/dev/null | sort -rh | head -10
du -sh /var/lib/*  2>/dev/null | sort -rh | head -10

# ============================================================
# QUICK WINS — Immediately free space (low risk)
# ============================================================

# 1. Truncate Slurm logs (keeps file handle, empties content)
truncate -s 0 /var/log/slurm/slurmctld.log 2>/dev/null
truncate -s 0 /var/log/slurm/slurmd.log 2>/dev/null
truncate -s 0 /var/log/slurm/slurmdbd.log 2>/dev/null
echo "Freed: Slurm logs truncated"

# 2. Truncate system logs
truncate -s 0 /var/log/messages 2>/dev/null
truncate -s 0 /var/log/syslog 2>/dev/null
truncate -s 0 /var/log/kern.log 2>/dev/null
echo "Freed: system logs truncated"

# 3. Clear old rotated logs
find /var/log -name "*.gz" -delete 2>/dev/null
find /var/log -name "*.old" -delete 2>/dev/null
find /var/log -name "*.[0-9]" -delete 2>/dev/null
find /var/log -name "*.xz" -delete 2>/dev/null
echo "Freed: rotated logs removed"

# 4. Shrink systemd journal
journalctl --vacuum-size=200M
echo "Freed: journal shrunk to 200MB"

# 5. Clear package manager cache
yum clean all 2>/dev/null; dnf clean all 2>/dev/null; apt clean 2>/dev/null
echo "Freed: package cache cleaned"

# 6. Remove old kernel crash dumps
rm -f /var/crash/vmcore.* 2>/dev/null
rm -rf /var/crash/127.0.0.1-* 2>/dev/null
echo "Freed: crash dumps removed"

# 7. Clean /tmp (if on same partition)
find /tmp -type f -mtime +2 -delete 2>/dev/null
echo "Freed: old temp files removed"

# ============================================================
# CHECK HOW MUCH SPACE YOU FREED
# ============================================================
df -h / /var
# You need at least a few GB free for XFS repair to work
```

### Step 3: Handle Deleted-But-Open Files

> [!WARNING]
> Even after deleting files, space may NOT be freed if a process still has the file open.
> This is one of the most common "I deleted files but disk is still full" traps.

```bash
# Find deleted files still held open by processes
lsof +L1 2>/dev/null | grep deleted | sort -k7 -rn | head -20
# Example output:
# slurmctld 1234 root 5w REG 8,1 5368709120 0 /var/log/slurm/slurmctld.log (deleted)
#                                 ^^^^^^^^^^ 5GB still held!

# The ONLY way to free this space is to restart the process holding it:
# If slurmctld is holding a deleted log file:
systemctl restart slurmctld    # Releases the file handle

# Or restart ALL Slurm services to release all handles:
systemctl restart slurmctld slurmdbd 2>/dev/null

# Or kill by PID from lsof output:
# kill <pid>    # Then the space is freed immediately

# Re-check:
df -h /var
```

### Step 4: Repair XFS After Freeing Space

```bash
# Now that / has free space, repair the loop filesystem:

# 1. Stop everything using /cm/shared
exportfs -ua
systemctl stop slurmctld slurmdbd 2>/dev/null
pdsh -w node[001-064] "systemctl stop slurmd; umount -l /cm/shared" 2>/dev/null

# 2. Unmount /cm/shared
umount /cm/shared 2>/dev/null || umount -l /cm/shared

# 3. Repair XFS (the shutdown was caused by ENOSPC, not real corruption)
xfs_repair /dev/loop0 2>&1 | tee /tmp/xfs_repair_after_full.log
# This should be FAST — the filesystem isn't truly corrupted,
# it just needs its journal cleaned up.

# If "dirty log" error:
xfs_repair -L /dev/loop0 2>&1 | tee /tmp/xfs_repair_L_after_full.log

# 4. Remount
mount /dev/loop0 /cm/shared
mount | grep loop0    # Verify: should show "rw"

# 5. Verify critical files survived
ls /cm/shared/apps/slurm/etc/slurm/plugstack.conf && echo "✓ plugstack.conf OK"
ls /cm/shared/apps/slurm/etc/slurm/slurm.conf && echo "✓ slurm.conf OK"
```

### Step 5: Restore Full Stack

```bash
# Re-export NFS
exportfs -a
exportfs -v | grep cm

# Remount on compute nodes
pdsh -w node[001-064] "mount /cm/shared" 2>&1 | dshbak -c
pdsh -w node[001-064] "cat /cm/shared/apps/slurm/etc/slurm/plugstack.conf > /dev/null && echo OK || echo FAIL" 2>&1 | dshbak -c

# Restart Slurm stack
systemctl start munge
systemctl start slurmdbd
sleep 5
systemctl start slurmctld

pdsh -w node[001-064] "systemctl restart munge && systemctl restart slurmd"

# Resume nodes
scontrol update NodeName=ALL State=RESUME
sinfo -N -l

# Test job submission
sbatch --wrap="hostname" -N1
squeue
echo "✓ Cluster recovered from disk-full event"
```

### Step 6: Prevent Recurrence

```bash
# ============================================================
# A. Configure log rotation for Slurm
# ============================================================
cat > /etc/logrotate.d/slurm << 'EOF'
/var/log/slurm/*.log {
    weekly
    rotate 4
    compress
    delaycompress
    missingok
    notifempty
    maxsize 500M
    postrotate
        /bin/kill -HUP $(cat /var/run/slurmctld.pid 2>/dev/null) 2>/dev/null || true
    endscript
}
EOF

# ============================================================
# B. Limit systemd journal size
# ============================================================
mkdir -p /etc/systemd/journald.conf.d/
cat > /etc/systemd/journald.conf.d/size-limit.conf << 'EOF'
[Journal]
SystemMaxUse=1G
SystemMaxFileSize=100M
MaxRetentionSec=7day
EOF
systemctl restart systemd-journald

# ============================================================
# C. Add disk space monitoring (cron every 15 min)
# ============================================================
cat > /etc/cron.d/disk-space-monitor << 'EOF'
# Alert if /var exceeds 85%
*/15 * * * * root USAGE=$(df /var --output=pcent | tail -1 | tr -d ' %'); [ "$USAGE" -gt 85 ] && echo "CRITICAL: /var is ${USAGE}% full on $(hostname)" | logger -p local0.crit
EOF

# ============================================================
# D. Set reserved blocks (EXT4 only — XFS doesn't have this)
# ============================================================
# If root filesystem is EXT4, reserve 5% for root:
# tune2fs -m 5 /dev/sda1

# ============================================================
# E. Consider moving large consumers to separate partition
# ============================================================
echo "Recommended: move /var/lib/mysql to a separate partition/LVM volume"
echo "Recommended: move /var/log/slurm to a separate partition"
echo "This prevents log growth from killing /cm/shared"
```

---

## 1. Emergency Stop (Run Before Any Repair)

> [!CAUTION]
> **Do this FIRST before any filesystem repair. Prevents cascading D-state hangs
> across all compute nodes.**

```bash
# ============================================================
# PHASE 1: Isolate /cm/shared from all consumers
# ============================================================

# 1a. Stop Slurm on head node
systemctl stop slurmctld 2>/dev/null
systemctl stop slurmdbd 2>/dev/null

# 1b. Unexport NFS shares (prevents new NFS requests from nodes)
exportfs -ua
echo "NFS exports removed — nodes can no longer access /cm/shared"

# 1c. Stop slurmd on ALL compute nodes (they'll hang on NFS otherwise)
# Use timeout to prevent pdsh from hanging if nodes are stuck
timeout 30 pdsh -w node[001-064] "systemctl stop slurmd; systemctl stop munge" 2>/dev/null
echo "If pdsh timed out, some nodes are already stuck in D-state on NFS"

# 1d. Force-unmount /cm/shared on compute nodes
timeout 30 pdsh -w node[001-064] "umount -l /cm/shared" 2>/dev/null

# 1e. Kill anything holding /cm/shared open on head node
fuser -vm /cm/shared 2>/dev/null
echo "Review above list — kill if safe:"
echo "  fuser -km /cm/shared    # KILLS all processes using /cm/shared"
echo "  # Or selectively: kill -9 <pid>"
```

---

## 2. XFS Filesystem Recovery (Most Common on RHEL/BCM)

### 2a. Identify the Device

```bash
# If df works:
df -hT /cm/shared
# Note: DEVICE and TYPE columns

# If df hangs (filesystem already inaccessible):
grep cm /etc/fstab
# Or:
mount | grep cm
# Or:
lsblk -f | grep -B2 -A2 cm

# Example output you might see:
# /dev/sda4 on /cm/shared type xfs (rw,relatime,attr2,inode64,logbufs=8)
# /dev/mapper/vg_cm-lv_shared on /cm/shared type xfs (rw,relatime)
```

### 2b. Check XFS State

```bash
DEVICE="/dev/sda4"    # ← REPLACE with your actual device from 2a

# Check if XFS has shut down its journal
dmesg -T | grep -i xfs | tail -30
# Key errors:
#   "Filesystem has been shut down due to log error"
#   "xlog_recover: modification to a logged... log replay failure"
#   "Metadata I/O error"
#   "writeback error"

# Check mount options — was it remounted read-only?
mount | grep cm
# If you see "(ro," instead of "(rw," → kernel forced read-only

# XFS filesystem metadata
xfs_info /cm/shared 2>/dev/null || echo "Cannot read XFS info — filesystem inaccessible"
```

### 2c. Unmount

```bash
# Normal unmount
umount /cm/shared

# If it hangs (processes stuck):
umount -l /cm/shared     # Lazy — detaches from namespace immediately
sleep 2

# If STILL shows as mounted:
umount -f /cm/shared     # Force

# Nuclear: if nothing works, processes are stuck in D-state
# These won't die with kill -9 (kernel I/O wait). You may need:
echo "If umount still fails, a REBOOT of the head node may be required"
echo "after repair steps are understood (see Section 8)"
```

### 2d. XFS Repair — Three Escalation Levels

```bash
DEVICE="/dev/sda4"    # ← REPLACE with your actual device

# ========== LEVEL 1: Dry Run (Safe, Read-Only) ==========
xfs_repair -n $DEVICE 2>&1 | tee /tmp/xfs_repair_dryrun.log
echo "Review /tmp/xfs_repair_dryrun.log for errors"
# If output says "No modify flag set, skipping..." and shows errors,
# you need Level 2.

# ========== LEVEL 2: Standard Repair ==========
xfs_repair $DEVICE 2>&1 | tee /tmp/xfs_repair.log
# This fixes:
#   - inode corruption
#   - directory entry errors
#   - free space map inconsistencies
#   - AG (allocation group) header errors

# If you get: "ERROR: The filesystem has valuable metadata changes in a log
#              which needs to be replayed..."
# This means the journal has un-committed transactions. Try:
mount $DEVICE /cm/shared && umount /cm/shared
# This replays the journal. Then re-run xfs_repair.

# ========== LEVEL 3: Zero the Journal (DATA LOSS RISK) ==========
# ONLY if Level 2 fails with "dirty log" errors:
xfs_repair -L $DEVICE 2>&1 | tee /tmp/xfs_repair_L.log
# -L = zero the log
# WARNING: This discards any un-committed transactions
# You WILL lose the last few seconds/minutes of writes before the crash

# ========== LEVEL 4: Aggressive Repair (Severe Corruption) ==========
xfs_repair -L -P $DEVICE 2>&1 | tee /tmp/xfs_repair_LP.log
# -P = disable prefetching (slower but handles severely damaged metadata)
```

### 2e. Post-Repair Validation

```bash
DEVICE="/dev/sda4"    # ← REPLACE

# Remount
mount $DEVICE /cm/shared
mount | grep cm     # Verify "rw" not "ro"

# Critical file checks
echo "===== Critical Slurm Files ====="
for f in \
    /cm/shared/apps/slurm/etc/slurm/slurm.conf \
    /cm/shared/apps/slurm/etc/slurm/plugstack.conf \
    /cm/shared/apps/slurm/etc/slurm/gres.conf \
    /cm/shared/apps/slurm/etc/slurm/cgroup.conf \
    /cm/shared/apps/munge/etc/munge/munge.key; do
    if [ -f "$f" ]; then
        echo "  ✓ $f ($(stat -c%s "$f") bytes)"
    else
        echo "  ✗ MISSING: $f"
    fi
done

echo ""
echo "===== Slurm Binaries ====="
ls -la /cm/shared/apps/slurm/current/bin/sinfo 2>/dev/null && echo "  ✓ Slurm binaries present" || echo "  ✗ Slurm binaries MISSING"
ls -la /cm/shared/apps/slurm/current/sbin/slurmd 2>/dev/null && echo "  ✓ slurmd present" || echo "  ✗ slurmd MISSING"

echo ""
echo "===== Lost+Found (repaired orphan files) ====="
ls -la /cm/shared/lost+found/ 2>/dev/null | head -10
# If files appeared here, xfs_repair recovered orphaned inodes.
# You may need to identify and move them back.
```

---

## 3. EXT4 Filesystem Recovery

```bash
DEVICE="/dev/sda4"    # ← REPLACE

# Unmount first (same as Section 2c)
umount /cm/shared || umount -l /cm/shared

# ========== Dry Run ==========
e2fsck -n $DEVICE 2>&1 | tee /tmp/e2fsck_dryrun.log

# ========== Standard Repair ==========
e2fsck -fy $DEVICE 2>&1 | tee /tmp/e2fsck.log
# -f = force check even if clean
# -y = auto-answer yes to all repairs

# ========== Superblock Recovery (if primary superblock is corrupt) ==========
# Find backup superblocks:
mke2fs -n $DEVICE 2>&1 | grep "Superblock backups"
# Then use a backup:
e2fsck -b 32768 -fy $DEVICE    # 32768 is a common backup superblock location

# Remount and validate (same as Section 2e)
mount $DEVICE /cm/shared
```

---

## 4. Hardware Disk Failure

If `dmesg` shows I/O errors on the actual block device (not just filesystem errors), the disk may be failing.

```bash
# ===== Identify the physical disk =====
DEVICE="/dev/sda4"
DISK="/dev/sda"       # Base disk (no partition number)

# ===== SMART Health =====
smartctl -a $DISK 2>&1 | tee /tmp/smart_report.txt
# Key fields to check:
smartctl -a $DISK | grep -E "Reallocated_Sector|Current_Pending|Offline_Uncorrectable|UDMA_CRC"
# ANY non-zero value on these = disk is dying

smartctl -H $DISK
# "PASSED" = OK (but check above counters)
# "FAILED" = REPLACE DISK IMMEDIATELY

# ===== Check for I/O errors in kernel log =====
dmesg -T | grep -i "$DISK\|medium error\|sense key\|not ready\|reset" | tail -30
# "medium error" = bad sectors
# "not ready"    = disk offline
# "reset"        = disk controller reset (cable or controller issue)

# ===== If RAID =====
cat /proc/mdstat
mdadm --detail /dev/md0 2>/dev/null
# Look for "degraded" or "removed" disks

# ===== If this is a hardware controller (MegaRAID, etc.) =====
# Check controller logs:
MegaCli64 -AdpAllInfo -aAll 2>/dev/null | head -50
storcli64 /c0 show 2>/dev/null
perccli64 /c0 show 2>/dev/null

# ===== Decision =====
echo "If disk is failing:"
echo "  1. DO NOT attempt fsck — it will make things worse"
echo "  2. Image/clone the disk to a healthy disk first:"
echo "     ddrescue /dev/sda /dev/sdb /tmp/rescue.log"
echo "  3. Run fsck on the CLONE"
echo "  4. Replace the failed disk, restore from clone or backup"
```

---

## 5. NFS Server Daemon Issues (Filesystem OK, NFS Broken)

If the filesystem is healthy but NFS is not serving `/cm/shared`:

```bash
# ===== NFS Server Status =====
systemctl status nfs-server -l --no-pager
systemctl status nfs-kernel-server -l --no-pager 2>/dev/null
systemctl status rpcbind -l --no-pager
systemctl status nfs-mountd -l --no-pager 2>/dev/null
systemctl status nfs-idmapd -l --no-pager 2>/dev/null

# ===== NFS kernel threads =====
ps aux | grep nfsd
# Should see multiple [nfsd] kernel threads. If zero → NFS is dead.

# How many NFS threads running? (default is often 8)
cat /proc/fs/nfsd/threads
# If 0 → NFS server is not serving anything

# ===== RPC services =====
rpcinfo -p localhost
# Should list: portmapper, nfs, mountd, nlockmgr
# If nfs or mountd missing → NFS server not registered

# ===== Exports =====
exportfs -v
# If empty → nothing is being shared
cat /etc/exports
# Should show /cm/shared with appropriate options

# ===== Restart NFS Stack =====
systemctl restart rpcbind
systemctl restart nfs-server     # or nfs-kernel-server

# Re-export
exportfs -a
exportfs -v | grep cm

# ===== Check NFS is listening =====
ss -tlnp | grep -E "2049|111"
# Port 2049 = NFS, Port 111 = rpcbind
# Both must be listening

# ===== NFS Stat Counters (look for errors) =====
nfsstat -s
# Check "badcalls" and "badauth" — should be 0 or very low
# High values = client authentication issues

# ===== Check NFS version being served =====
rpcinfo -p localhost | grep nfs
# Should show versions 3 and/or 4
cat /proc/fs/nfsd/versions
# Example: +2 +3 +4 +4.1 +4.2
```

---

## 6. Stale NFS Handle (Filesystem + NFS OK, But Clients Can't Access)

```bash
# ===== FROM HEAD NODE: verify local access works =====
ls -la /cm/shared/apps/slurm/
cat /cm/shared/apps/slurm/etc/slurm/plugstack.conf
# If this works locally → NFS export/client side issue

# ===== Check export options =====
exportfs -v
# Look for:
#   /cm/shared  *(rw,sync,no_root_squash,no_subtree_check)
# no_root_squash is important for Slurm/munge

# ===== Check client-side NFS mount options =====
pdsh -w node001 "mount | grep cm" 2>&1
# Note: hard vs soft mount, timeout values
# "hard" mounts will hang forever if NFS is down
# "soft" mounts will return EIO — which is your SPANK error!

# ===== Force re-export with flush =====
exportfs -r    # Re-export all, synchronizing /var/lib/nfs/etab with /etc/exports

# ===== NFS file handle cache — clear stale entries =====
# Sometimes the NFS file handle mapping goes stale. Unexport and re-export:
exportfs -ua    # Remove all exports
sleep 2
exportfs -a     # Re-export all
sleep 2

# ===== Remount on a single test node =====
ssh node001
umount -l /cm/shared
mount -v /cm/shared     # -v for verbose mount output
ls /cm/shared/apps/slurm/etc/slurm/plugstack.conf
# If this works → roll out to all nodes
exit

# ===== Roll out to all nodes =====
pdsh -w node[001-064] "umount -l /cm/shared; sleep 1; mount /cm/shared" 2>&1 | dshbak -c
pdsh -w node[001-064] "cat /cm/shared/apps/slurm/etc/slurm/plugstack.conf > /dev/null && echo OK || echo FAIL" 2>&1 | dshbak -c
```

---

## 7. Full Debug Walkthrough (Nothing Obvious)

When `dmesg` is clean and nothing looks obviously broken, walk through this systematically:

```bash
# ===== Layer 1: Physical Disk =====
lsblk -f
smartctl -H /dev/sda
cat /proc/mdstat 2>/dev/null
lvs 2>/dev/null

# ===== Layer 2: Filesystem =====
mount | grep cm
touch /cm/shared/.health_check 2>&1     # Can we write?
rm /cm/shared/.health_check 2>&1
time ls /cm/shared/ > /dev/null         # Is it slow?

# ===== Layer 3: NFS Server =====
systemctl is-active nfs-server
exportfs -v | grep cm
ss -tlnp | grep 2049
rpcinfo -p localhost | grep nfs

# ===== Layer 4: NFS Client (from a node) =====
ssh node001 "mount | grep cm; ls /cm/shared/ > /dev/null 2>&1 && echo OK || echo FAIL"

# ===== Layer 5: Slurm Dependencies =====
ls -la /cm/shared/apps/slurm/etc/slurm/plugstack.conf
ls -la /cm/shared/apps/slurm/current/bin/sinfo
ls -la /cm/shared/apps/munge/

# ===== Layer 6: Check Logs Chronologically =====
# What happened first? Find the root cause event.
journalctl --since "6 hours ago" | grep -iE "error|fail|corrupt|nfs|xfs|ext4|shutdown|restart" | head -50
```

---

## 8. Head Node Reboot Recovery (Last Resort)

> [!CAUTION]
> **Only reboot the head node if filesystem repair cannot be done online.**
> A head node reboot takes down ALL BCM management, provisioning, and monitoring.

### Pre-Reboot Checklist

```bash
# 1. Document current state
dmesg -T > /tmp/pre-reboot-dmesg.txt
mount > /tmp/pre-reboot-mounts.txt
exportfs -v > /tmp/pre-reboot-exports.txt
cp /etc/exports /tmp/pre-reboot-exports-file.txt
cp /etc/fstab /tmp/pre-reboot-fstab.txt
systemctl list-units --state=running > /tmp/pre-reboot-services.txt

# 2. Save to a location that survives reboot (NOT on /cm/shared!)
ls /tmp/pre-reboot-*.txt

# 3. Ensure compute nodes won't panic
# If nodes are diskless, they boot from head node — rebooting head node
# won't kill them if they're already booted, but new boots will fail.
pdsh -w node[001-064] "systemctl stop slurmd; umount -l /cm/shared" 2>/dev/null
```

### Reboot + Recovery

```bash
# Option A: Clean reboot
reboot

# Option B: Force reboot (if system is hung)
echo b > /proc/sysrq-trigger
# Or:
ipmitool chassis power cycle    # If you have IPMI/BMC access
```

### Post-Reboot Recovery

```bash
# 1. Verify filesystem was auto-repaired or needs manual repair
dmesg -T | grep -iE "xfs|ext4|error|repair|fsck" | tail -20

# 2. If /cm/shared didn't mount automatically:
mount | grep cm
# If not mounted:
fsck /dev/sda4        # or xfs_repair /dev/sda4
mount /cm/shared

# 3. Verify NFS exports came back
exportfs -v | grep cm
# If empty:
exportfs -a

# 4. Verify critical BCM services
systemctl status cmd         # BCM daemon
systemctl status nfs-server
systemctl status slurmctld
systemctl status slurmdbd
systemctl status munge

# 5. Restart anything that didn't come back
systemctl start cmd
systemctl start nfs-server
systemctl start munge
systemctl start slurmdbd
sleep 5
systemctl start slurmctld

# 6. Re-mount on compute nodes
pdsh -w node[001-064] "mount /cm/shared" 2>&1 | dshbak -c
pdsh -w node[001-064] "systemctl restart munge && systemctl restart slurmd" 2>&1 | dshbak -c

# 7. Final verification
scontrol ping
sinfo -N -l
scontrol update NodeName=ALL State=RESUME
sbatch --wrap="hostname" -N1
squeue
echo "✓ Cluster recovered"
```

---

## 9. BCM-Specific Recovery Commands

If `/cm/shared` data was lost or corrupted beyond repair:

```bash
# ===== Regenerate Slurm Config from BCM =====
cmsh
wlm
# Check current state
show
# Re-deploy Slurm configuration
assign slurm
commit
quit

# ===== Re-provision Node Overlays =====
# This pushes fresh configs to all nodes from the BCM image
cmsh -c "device; foreach -n node* (imageupdate)"

# ===== Regenerate Munge Key =====
systemctl stop munge
create-munge-key --force
systemctl start munge

# Distribute via BCM:
cmsh -c "device; foreach -n node* (imageupdate)"
# Or manually:
pdsh -w node[001-064] "systemctl stop munge"
pdcp -w node[001-064] /etc/munge/munge.key /etc/munge/munge.key
pdsh -w node[001-064] "chown munge:munge /etc/munge/munge.key; chmod 400 /etc/munge/munge.key; systemctl start munge"

# ===== Check BCM's own backup of /cm/shared =====
# BCM stores some config backups at:
ls /cm/node-installer/ 2>/dev/null
ls /var/spool/cmd/ 2>/dev/null

# ===== If /cm/shared was on a separate LVM volume and LVM is damaged =====
vgcfgrestore vg_cm                       # Restore VG metadata from auto-backup
lvchange -ay /dev/vg_cm/lv_shared        # Activate the LV
xfs_repair /dev/vg_cm/lv_shared          # Repair filesystem
mount /dev/vg_cm/lv_shared /cm/shared    # Remount
```

---

## Quick Reference: Error → Root Cause → Fix

| Error Message | Root Cause | Immediate Fix |
|--------------|------------|---------------|
| `Input/output error` on `/cm/shared/*` | NFS stale handle OR filesystem corruption | Check `dmesg` → fsck or remount |
| `Stale file handle` | NFS export changed or server restarted | `exportfs -r` on head, remount on nodes |
| `Structure needs cleaning` | Filesystem metadata corruption | Unmount + `xfs_repair` or `e2fsck` |
| `XFS: Filesystem has been shut down` | XFS journal failure | `umount` + `xfs_repair -L` |
| `EXT4-fs error: remounting read-only` | EXT4 detected corruption | `umount` + `e2fsck -fy` |
| `No space left on device` | `/cm/shared` full | `df -h /cm/shared` → clean up old data |
| `Permission denied` on NFS mount | `root_squash` enabled in exports | Add `no_root_squash` to `/etc/exports` |
| `mount.nfs: access denied by server` | Export removed or IP not allowed | Check `/etc/exports`, run `exportfs -a` |
| `RPC: Port mapper failure` | `rpcbind` not running | `systemctl restart rpcbind` |
| `NFSD: Unable to create proc entry` | NFS kernel module issue | `modprobe nfsd`, restart nfs-server |
| `medium error` in dmesg | Physical disk sector failure | **Replace disk**, clone first with `ddrescue` |
| `losetup -a` shows no `/dev/loop0` | Loop device detached from backing image | `losetup /dev/loop0 <image>` then mount |
| Loop backing file returns I/O error | **Parent filesystem corrupt** (loop image damaged) | Repair parent FS first, then `xfs_repair /dev/loop0` |
| `SPANK: plugstack.conf: Input/output error` | NFS stale or loop → parent FS corrupt | Trace: loop0 → backing file → parent FS |

---

> [!IMPORTANT]
> **Post-Recovery**: After the cluster is back, schedule a maintenance window to run
> a full filesystem check (`xfs_repair -n` or `e2fsck -n`) and SMART long test
> (`smartctl -t long /dev/sda`). Filesystem corruption that happens once often indicates
> an underlying hardware issue (failing disk, bad controller, power loss) that WILL
> recur.

# BCM Installation Guide

## Quick Start

### Prerequisites
- KVM/libvirt installed (`apt install qemu-kvm libvirt-daemon-system`)
- BCM 11 ISO downloaded to `/home/user/vm-images/bcm-11.0-ubuntu2404.iso`
- Product key from NVIDIA/Bright Computing

### Step 1: Create Network
```bash
./scripts/01-create-networks.sh
```

### Step 2: Create Head Node
```bash
./scripts/02-create-head-node.sh
```

### Step 3: Install BCM
1. Open console: `virt-viewer bcm-head`
2. Select **"Start graphical installer"**
3. Follow wizard:
   - Accept license
   - Set root password
   - NIC assignment: external = first NIC, internal = second NIC (192.168.200.0/24)
   - Disk: default layout
   - Wait for installation (~20 min)
4. VM reboots automatically

### Step 4: Create Compute Nodes
```bash
./scripts/03-create-cpu-nodes.sh
./scripts/04-create-gpu-node.sh
```

### Step 5: Configure Slurm
1. Login to head node: `virt-viewer bcm-head` → root / your-password
2. Run: `cmsh`
3. Follow commands in `configs/slurm-setup.cmsh`

### Step 6: Boot Compute Nodes
```bash
virsh start cpu-n01
virsh start cpu-n02
virsh start gpu-n01
```
BCM will PXE boot and provision them automatically.

### Step 7: Verify
```bash
# On the head node:
sinfo              # Check node status
squeue             # Check job queue
sbatch --wrap="hostname"  # Submit test job
```

## Troubleshooting

### Compute Nodes Not PXE Booting
- Ensure bcm-mgmt network is active: `virsh net-list`
- Check BCM DHCP: `journalctl -u dhcpd` on head node
- Verify nodes boot order: network first

### SSH Not Working
- Login via `virt-viewer bcm-head`
- Run: `shorewall stop` (disables firewall)
- Check SSH: `systemctl status sshd`

### GPU Not Visible in VM
- See `configs/gpu-passthrough.md` for IOMMU/VFIO setup

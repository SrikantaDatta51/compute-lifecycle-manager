# GPU Passthrough: Quadro GV100

## Hardware

| Property | Value |
|----------|-------|
| GPU | NVIDIA Quadro GV100 |
| PCI | `4f:00.0` (GPU) + `4f:00.1` (Audio) |
| PCI IDs | `10de:1dba` (GPU), `10de:10f2` (Audio) |
| VRAM | 32 GB HBM2 |

## Prerequisites for Passthrough

### 1. Enable IOMMU in GRUB

```bash
sudo vim /etc/default/grub
# Add to GRUB_CMDLINE_LINUX:
GRUB_CMDLINE_LINUX="intel_iommu=on iommu=pt"

sudo update-grub
sudo reboot
```

### 2. Verify IOMMU is Active

```bash
dmesg | grep -i iommu
# Should show: "DMAR: IOMMU enabled"
```

### 3. Bind GPU to VFIO Driver

```bash
# Load VFIO modules
sudo modprobe vfio-pci

# Unbind from nvidia driver
echo "0000:4f:00.0" | sudo tee /sys/bus/pci/devices/0000:4f:00.0/driver/unbind
echo "0000:4f:00.1" | sudo tee /sys/bus/pci/devices/0000:4f:00.1/driver/unbind

# Bind to vfio-pci
echo "10de 1dba" | sudo tee /sys/bus/pci/drivers/vfio-pci/new_id
echo "10de 10f2" | sudo tee /sys/bus/pci/drivers/vfio-pci/new_id
```

### 4. Persistent VFIO Binding

Create `/etc/modprobe.d/vfio.conf`:
```
options vfio-pci ids=10de:1dba,10de:10f2
```

Create `/etc/modules-load.d/vfio.conf`:
```
vfio-pci
```

## Adding GPU to VM After Creation

If the VM was created without GPU passthrough, attach it manually:

```bash
# Create XML for the GPU device
cat > /tmp/gpu-device.xml << 'EOF'
<hostdev mode='subsystem' type='pci' managed='yes'>
  <source>
    <address domain='0x0000' bus='0x4f' slot='0x00' function='0x0'/>
  </source>
</hostdev>
EOF

cat > /tmp/gpu-audio.xml << 'EOF'
<hostdev mode='subsystem' type='pci' managed='yes'>
  <source>
    <address domain='0x0000' bus='0x4f' slot='0x00' function='0x1'/>
  </source>
</hostdev>
EOF

# Attach to VM
virsh attach-device gpu-n01 /tmp/gpu-device.xml --config
virsh attach-device gpu-n01 /tmp/gpu-audio.xml --config
```

## Verification Inside VM

```bash
# After VM boots and is provisioned, verify GPU is visible:
lspci | grep -i nvidia
nvidia-smi
```

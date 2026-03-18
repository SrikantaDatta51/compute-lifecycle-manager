#!/bin/bash
# Create GPU compute node VM with Quadro GV100 passthrough
# This VM PXE boots from BCM and has the GV100 GPU passed through
set -e

NAME="gpu-n01"
DISK_DIR="/home/user/vm-images"
DISK="${DISK_DIR}/${NAME}.qcow2"
NETWORK="bcm-mgmt"

# GPU PCI addresses (Quadro GV100)
GPU_PCI="4f:00.0"
GPU_AUDIO_PCI="4f:00.1"

echo "=== Creating GPU Node: ${NAME} ==="

# Step 1: Check IOMMU
if ! dmesg 2>/dev/null | grep -qi "iommu"; then
    echo "WARNING: IOMMU may not be enabled in BIOS/GRUB"
    echo "For GPU passthrough, ensure intel_iommu=on in GRUB cmdline"
    echo "  Edit /etc/default/grub: GRUB_CMDLINE_LINUX=\"intel_iommu=on iommu=pt\""
    echo "  Then: update-grub && reboot"
    echo ""
fi

# Step 2: Create disk
if [ ! -f "$DISK" ]; then
    qemu-img create -f qcow2 "$DISK" 30G
    echo "  Disk created: ${DISK}"
else
    echo "  Disk already exists: ${DISK}"
fi

# Step 3: Check if VM exists
if virsh dominfo "$NAME" &>/dev/null; then
    echo "  VM ${NAME} already exists"
    echo "  To recreate: virsh destroy ${NAME}; virsh undefine ${NAME} --nvram"
    exit 0
fi

# Step 4: Try to create with GPU passthrough
echo "  Attempting GPU passthrough (PCI ${GPU_PCI})..."

# First try with GPU passthrough
if virt-install \
    --name "$NAME" \
    --vcpus 4 \
    --memory 4096 \
    --disk "path=${DISK},format=qcow2,bus=virtio" \
    --network network="${NETWORK}",model=virtio \
    --os-variant ubuntu24.04 \
    --pxe \
    --boot network,hd \
    --graphics vnc,listen=0.0.0.0 \
    --host-device "pci_0000_${GPU_PCI//:/_}" \
    --host-device "pci_0000_${GPU_AUDIO_PCI//:/_}" \
    --features kvm_hidden=on \
    --noautoconsole \
    --noreboot 2>/dev/null; then
    echo "  GPU passthrough configured successfully!"
else
    echo "  GPU passthrough failed (IOMMU/VFIO not available)"
    echo "  Creating VM WITHOUT GPU passthrough..."
    echo "  You can add the GPU later with: virsh attach-device"

    virt-install \
        --name "$NAME" \
        --vcpus 4 \
        --memory 4096 \
        --disk "path=${DISK},format=qcow2,bus=virtio" \
        --network network="${NETWORK}",model=virtio \
        --os-variant ubuntu24.04 \
        --pxe \
        --boot network,hd \
        --graphics vnc,listen=0.0.0.0 \
        --noautoconsole \
        --noreboot

    echo "  VM created without GPU. See configs/gpu-passthrough.md for manual steps."
fi

echo ""
echo "=== GPU Node Created ==="
echo "Start with: virsh start ${NAME}"
echo "BCM will detect and provision it via PXE boot."

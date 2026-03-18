#!/bin/bash
# Create BCM head node VM
# Requires: BCM 11 ISO already downloaded
set -e

NAME="bcm-head"
DISK_DIR="/home/user/vm-images"
DISK="${DISK_DIR}/${NAME}.qcow2"
ISO="${DISK_DIR}/bcm-11.0-ubuntu2404.iso"

echo "=== Creating BCM Head Node ==="

# Check ISO
if [ ! -f "$ISO" ]; then
    echo "ERROR: BCM ISO not found at ${ISO}"
    echo "Download from: https://customer.brightcomputing.com/download-iso"
    exit 1
fi

# Create disk
if [ ! -f "$DISK" ]; then
    qemu-img create -f qcow2 "$DISK" 200G
    echo "  Disk created: ${DISK}"
fi

# Check if VM exists
if virsh dominfo "$NAME" &>/dev/null; then
    echo "  VM ${NAME} already exists"
    exit 0
fi

# Create VM
virt-install \
    --name "$NAME" \
    --vcpus 16 \
    --memory 49152 \
    --disk "path=${DISK},format=qcow2,bus=virtio" \
    --cdrom "$ISO" \
    --network network=default,model=virtio \
    --network network=bcm-mgmt,model=virtio \
    --os-variant ubuntu24.04 \
    --graphics vnc,listen=0.0.0.0 \
    --noautoconsole

echo ""
echo "=== BCM Head Node Created ==="
echo "Connect to installer: virt-viewer ${NAME}"
echo "Select 'Start graphical installer' from boot menu"

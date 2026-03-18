#!/bin/bash
# Create CPU compute node VMs for BCM provisioning
# These boot from network (PXE) so BCM can provision them
set -e

DISK_DIR="/home/user/vm-images"
NETWORK="bcm-mgmt"

for i in 1 2; do
    NAME="cpu-n0${i}"
    DISK="${DISK_DIR}/${NAME}.qcow2"

    echo "=== Creating ${NAME} ==="

    # Create disk image
    if [ ! -f "$DISK" ]; then
        qemu-img create -f qcow2 "$DISK" 20G
        echo "  Disk created: ${DISK}"
    else
        echo "  Disk already exists: ${DISK}"
    fi

    # Check if VM already exists
    if virsh dominfo "$NAME" &>/dev/null; then
        echo "  VM ${NAME} already exists, skipping"
        continue
    fi

    # Create VM - PXE boot from bcm-mgmt network
    virt-install \
        --name "$NAME" \
        --vcpus 2 \
        --memory 2048 \
        --disk "path=${DISK},format=qcow2,bus=virtio" \
        --network network="${NETWORK}",model=virtio \
        --os-variant ubuntu24.04 \
        --pxe \
        --boot network,hd \
        --graphics vnc,listen=0.0.0.0 \
        --noautoconsole \
        --noreboot

    echo "  VM ${NAME} created successfully"
done

echo ""
echo "=== CPU Nodes Created ==="
echo "Both nodes will PXE boot from BCM head node."
echo "Start them with: virsh start cpu-n01 && virsh start cpu-n02"
echo "BCM will detect and provision them automatically."

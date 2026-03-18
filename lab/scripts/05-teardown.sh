#!/bin/bash
# Teardown all BCM lab VMs and networks
set -e

echo "=== BCM Lab Teardown ==="
echo "This will destroy all VMs and clean up resources."
read -p "Are you sure? (y/N): " confirm
[ "$confirm" != "y" ] && echo "Aborted." && exit 0

DISK_DIR="/home/user/vm-images"

for VM in gpu-n01 cpu-n02 cpu-n01 bcm-head; do
    if virsh dominfo "$VM" &>/dev/null; then
        virsh destroy "$VM" 2>/dev/null || true
        virsh undefine "$VM" --nvram 2>/dev/null || virsh undefine "$VM" 2>/dev/null
        echo "  Removed VM: ${VM}"
    fi
done

# Remove disk images
for DISK in bcm-head.qcow2 cpu-n01.qcow2 cpu-n02.qcow2 gpu-n01.qcow2; do
    rm -f "${DISK_DIR}/${DISK}"
    echo "  Removed disk: ${DISK}"
done

# Remove network
virsh net-destroy bcm-mgmt 2>/dev/null || true
virsh net-undefine bcm-mgmt 2>/dev/null || true
echo "  Removed network: bcm-mgmt"

echo ""
echo "=== Teardown Complete ==="

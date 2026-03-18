#!/bin/bash
# Create the bcm-mgmt network for BCM provisioning
set -e

NETXML="/home/user/.gemini/antigravity/scratch/bcm-lab/configs/bcm-mgmt-net.xml"

echo "=== Creating BCM Management Network ==="

if virsh net-info bcm-mgmt &>/dev/null; then
    echo "  bcm-mgmt network already exists"
    virsh net-info bcm-mgmt
else
    virsh net-define "$NETXML"
    virsh net-start bcm-mgmt
    virsh net-autostart bcm-mgmt
    echo "  bcm-mgmt network created and started"
fi

echo ""
virsh net-list --all

#!/bin/bash
set -e

# ============================================
# OverBranch — Build Local, Deploy to VM
# ============================================
# No GitHub Actions, no registry, no payments.
# Builds locally → saves as file → copies to VM → runs.
#
# Usage: ./deploy.sh
# ============================================

IMAGE_NAME="overbranch"
IMAGE_FILE="overbranch-image.tar.gz"

# --- Config: Change these ---
VM_USER="${AZURE_VM_USERNAME:-abin}"
VM_IP="${AZURE_VM_IP:-your-vm-ip}"
VM_DIR="~/overbranch"
# ----------------------------

echo ""
echo "══════════════════════════════════════════"
echo "  Step 1/4: Build Docker image locally"
echo "══════════════════════════════════════════"
docker compose build

echo ""
echo "══════════════════════════════════════════"
echo "  Step 2/4: Save image to file"
echo "══════════════════════════════════════════"
docker save "$IMAGE_NAME" | gzip > "$IMAGE_FILE"
echo "  Saved: $IMAGE_FILE ($(du -h "$IMAGE_FILE" | cut -f1))"

echo ""
echo "══════════════════════════════════════════"
echo "  Step 3/4: Copy to VM via scp"
echo "══════════════════════════════════════════"
scp "$IMAGE_FILE" "$VM_USER@$VM_IP:$VM_DIR/$IMAGE_FILE"

echo ""
echo "══════════════════════════════════════════"
echo "  Step 4/4: Load & restart on VM"
echo "══════════════════════════════════════════"
ssh "$VM_USER@$VM_IP" bash -s <<REMOTE
  set -e
  cd $VM_DIR

  echo "Loading image..."
  docker load < $IMAGE_FILE

  echo "Restarting container..."
  docker compose down
  docker compose up -d --no-build

  echo "Cleaning up..."
  rm -f $IMAGE_FILE
  docker image prune -f

  echo ""
  echo "✓ Running containers:"
  docker compose ps
REMOTE

# Clean local tar
rm -f "$IMAGE_FILE"

echo ""
echo "══════════════════════════════════════════"
echo "  ✓ Done! Same image from your laptop"
echo "    is now running on $VM_IP"
echo "══════════════════════════════════════════"

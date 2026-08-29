#!/bin/bash
set -e

# ============================================
# OverBranch — Local Build & VM Deploy Script
# ============================================
# Uses standard `docker build` (no docker-compose needed on local machine)
# Saves image → transfers via scp → loads on VM
# ============================================

IMAGE_NAME="overbranch:latest"
IMAGE_FILE="overbranch-image.tar.gz"

# --- Config: Change these ---
VM_USER="${AZURE_VM_USERNAME:-abin}"
VM_IP="${AZURE_VM_IP:-your-vm-ip}"
VM_DIR="~/overbranch"
# ----------------------------

# Check if Docker daemon is running
if ! docker info >/dev/null 2>&1; then
  echo "Error: Docker daemon is not running."
  echo "Please start Docker with:  sudo systemctl start docker"
  exit 1
fi

echo ""
echo "══════════════════════════════════════════"
echo "  Step 1/4: Build Docker image locally"
echo "══════════════════════════════════════════"
docker build -t "$IMAGE_NAME" .

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

  # Remote compose detection (docker compose vs docker-compose)
  if docker compose version >/dev/null 2>&1; then
    R_COMPOSE="docker compose"
  else
    R_COMPOSE="docker-compose"
  fi

  echo "Loading image on VM..."
  docker load < $IMAGE_FILE

  echo "Restarting container..."
  \$R_COMPOSE down || true
  \$R_COMPOSE up -d --no-build

  echo "Cleaning up remote temp file..."
  rm -f $IMAGE_FILE
  docker image prune -f

  echo ""
  echo "✓ Running containers on VM:"
  \$R_COMPOSE ps
REMOTE

# Clean local tar
rm -f "$IMAGE_FILE"

echo ""
echo "══════════════════════════════════════════"
echo "  ✓ Done! Exact image built locally"
echo "    is now live on $VM_IP"
echo "══════════════════════════════════════════"

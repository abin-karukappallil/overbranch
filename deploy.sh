#!/bin/bash
set -e

# ============================================
# OverBranch — Build Local, Deploy to VM
# ============================================
# Usage: ./deploy.sh
#
# Prerequisites (one-time):
#   1. Login to GitHub Container Registry:
#      echo "YOUR_GITHUB_PAT" | docker login ghcr.io -u abin-karukappallil --password-stdin
#
#   2. On your VM, also login:
#      ssh user@vm-ip 'echo "YOUR_GITHUB_PAT" | docker login ghcr.io -u abin-karukappallil --password-stdin'
#
# To create a GitHub PAT:
#   GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
#   Scopes needed: write:packages, read:packages
# ============================================

IMAGE="ghcr.io/abin-karukappallil/overbranch:latest"

# --- Config: Change these ---
VM_USER="${AZURE_VM_USERNAME:-abin}"
VM_IP="${AZURE_VM_IP:-your-vm-ip}"
VM_DIR="~/overbranch"
# ----------------------------

echo ""
echo "══════════════════════════════════════════"
echo "  Step 1: Build Docker image locally"
echo "══════════════════════════════════════════"
docker compose build
docker tag overbranch "$IMAGE" 2>/dev/null || docker tag "$(docker compose images -q overbranch)" "$IMAGE"

echo ""
echo "══════════════════════════════════════════"
echo "  Step 2: Push image to ghcr.io"
echo "══════════════════════════════════════════"
docker push "$IMAGE"

echo ""
echo "══════════════════════════════════════════"
echo "  Step 3: Deploy on Azure VM"
echo "══════════════════════════════════════════"
ssh "$VM_USER@$VM_IP" bash -s <<REMOTE
  set -e
  cd $VM_DIR

  # Pull the pre-built image
  docker pull $IMAGE

  # Restart with the new image (no build on server)
  docker compose down
  docker compose up -d --no-build

  echo ""
  echo "✓ Deployed! Checking status..."
  docker compose ps
REMOTE

echo ""
echo "══════════════════════════════════════════"
echo "  ✓ Done! Your exact local build is live."
echo "══════════════════════════════════════════"

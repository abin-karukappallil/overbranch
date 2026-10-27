#!/bin/bash
set -e

# ============================================
# OverBranch — Local Build & VM Deploy Script
# ============================================
# TeX Live is a separate, slow-changing base image (docker/texlive.Dockerfile,
# ~5 GB). The app image is built FROM it, so an app deploy only needs to ship
# the app layers, not TeX.
#
# Default deploy path ("registry"): push to a registry running on the VM,
# reached over an SSH tunnel, so Docker's layer dedup means TeX Live uploads
# once and later deploys send only the changed app layers.
#
# Legacy path ("--scp"): docker save | gzip | scp the whole image (what this
# script used to do). Simple, but re-ships ~6 GB every time.
#
# Usage:
#   ./deploy.sh                 # build (base if missing) + registry deploy
#   ./deploy.sh --scp           # build + save/scp the whole image
#   ./deploy.sh --rebuild-tex   # force a rebuild of the TeX base first
# ============================================

TEX_IMAGE="${TEX_IMAGE:-overbranch-texlive:2026.1}"
IMAGE_NAME="overbranch:latest"
GIT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo latest)"
IMAGE_FILE="overbranch-image.tar.gz"

# --- Config: Change these ---
VM_USER="${AZURE_VM_USERNAME:-abin}"
VM_IP="${AZURE_VM_IP:-your-vm-ip}"
VM_DIR="~/overbranch"
REGISTRY_PORT="${REGISTRY_PORT:-5000}"   # registry:2 on the VM, bound to 127.0.0.1
# ----------------------------

MODE="registry"
REBUILD_TEX=0
for arg in "$@"; do
  case "$arg" in
    --scp) MODE="scp" ;;
    --rebuild-tex) REBUILD_TEX=1 ;;
    *) echo "Unknown option: $arg"; exit 1 ;;
  esac
done

# Check if Docker daemon is running
if ! docker info >/dev/null 2>&1; then
  echo "Error: Docker daemon is not running."
  echo "Please start Docker with:  sudo systemctl start docker"
  exit 1
fi

# ──────────────────────────────────────────
# Step 1: Build the TeX base image if needed
# ──────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════"
echo "  Step 1: TeX base image ($TEX_IMAGE)"
echo "══════════════════════════════════════════"
if [ "$REBUILD_TEX" = "1" ] || ! docker image inspect "$TEX_IMAGE" >/dev/null 2>&1; then
  echo "  Building $TEX_IMAGE (this is slow: full TeX Live + fonts)…"
  docker build -f docker/texlive.Dockerfile -t "$TEX_IMAGE" .
else
  echo "  $TEX_IMAGE already present — reusing (pass --rebuild-tex to force)."
fi

# ──────────────────────────────────────────
# Step 2: Build the app image on top of the base
# ──────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════"
echo "  Step 2: Build app image"
echo "══════════════════════════════════════════"
docker build --build-arg "TEX_BASE=$TEX_IMAGE" -t "$IMAGE_NAME" -t "overbranch:$GIT_SHA" .

if [ "$MODE" = "scp" ]; then
  # ────────────────────────────────────────
  # Legacy: save → scp → load (ships everything)
  # ────────────────────────────────────────
  echo ""
  echo "══════════════════════════════════════════"
  echo "  Step 3 (scp): Save image to file"
  echo "══════════════════════════════════════════"
  docker save "$IMAGE_NAME" | gzip > "$IMAGE_FILE"
  echo "  Saved: $IMAGE_FILE ($(du -h "$IMAGE_FILE" | cut -f1))"

  echo ""
  echo "  Copying to VM via scp…"
  scp "$IMAGE_FILE" "$VM_USER@$VM_IP:$VM_DIR/$IMAGE_FILE"

  echo ""
  echo "  Loading & restarting on VM…"
  ssh "$VM_USER@$VM_IP" bash -s <<REMOTE
    set -e
    cd $VM_DIR
    if docker compose version >/dev/null 2>&1; then R_COMPOSE="docker compose"; else R_COMPOSE="docker-compose"; fi
    docker load < $IMAGE_FILE
    \$R_COMPOSE down || true
    \$R_COMPOSE up -d --no-build
    rm -f $IMAGE_FILE
    docker image prune -f
    \$R_COMPOSE ps
REMOTE
  rm -f "$IMAGE_FILE"
else
  # ────────────────────────────────────────
  # Default: push through an SSH-tunnelled registry on the VM.
  # Only the app layers that changed are actually uploaded.
  # ────────────────────────────────────────
  echo ""
  echo "══════════════════════════════════════════"
  echo "  Step 3 (registry): ensure registry on VM + tunnel"
  echo "══════════════════════════════════════════"
  ssh "$VM_USER@$VM_IP" '
    set -e
    if ! docker ps --format "{{.Names}}" | grep -qx ob-registry; then
      docker run -d --restart=always --name ob-registry \
        -p 127.0.0.1:'"$REGISTRY_PORT"':5000 \
        -v ob-registry-data:/var/lib/registry registry:2
    fi
  '

  # Open a local→VM tunnel so `localhost:PORT` on this machine is the VM registry.
  # Backgrounded (not -f) so we hold the PID and can close it on exit.
  ssh -N -L "$REGISTRY_PORT:127.0.0.1:$REGISTRY_PORT" "$VM_USER@$VM_IP" &
  TUNNEL_PID=$!
  trap '[ -n "$TUNNEL_PID" ] && kill "$TUNNEL_PID" 2>/dev/null || true' EXIT
  sleep 2  # let the tunnel come up before the push

  echo "  Pushing overbranch:$GIT_SHA → localhost:$REGISTRY_PORT (only changed layers upload)…"
  docker tag "$IMAGE_NAME" "localhost:$REGISTRY_PORT/overbranch:$GIT_SHA"
  docker push "localhost:$REGISTRY_PORT/overbranch:$GIT_SHA"

  echo ""
  echo "══════════════════════════════════════════"
  echo "  Step 4 (registry): pull + restart on VM"
  echo "══════════════════════════════════════════"
  ssh "$VM_USER@$VM_IP" bash -s <<REMOTE
    set -e
    cd $VM_DIR
    if docker compose version >/dev/null 2>&1; then R_COMPOSE="docker compose"; else R_COMPOSE="docker-compose"; fi
    docker pull 127.0.0.1:$REGISTRY_PORT/overbranch:$GIT_SHA
    docker tag  127.0.0.1:$REGISTRY_PORT/overbranch:$GIT_SHA overbranch:latest
    \$R_COMPOSE down || true
    DOCKER_IMAGE=overbranch:latest \$R_COMPOSE up -d --no-build
    docker image prune -f
    \$R_COMPOSE ps
REMOTE
fi

echo ""
echo "══════════════════════════════════════════"
echo "  ✓ Done! overbranch:$GIT_SHA is live on $VM_IP"
echo "══════════════════════════════════════════"
echo ""
echo "  NOTE: the VM needs the registry's insecure-registry allowance for"
echo "  127.0.0.1:$REGISTRY_PORT (it's loopback, so Docker permits it by default)."
echo "  First deploy pushes the full ~6 GB; later deploys push only app layers."
echo "  Disk on the VM: budget ~12 GB for the image + registry volume."

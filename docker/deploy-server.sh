#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [[ -n ${DEPLOY_ENV_FILE:-} ]]; then
  echo "[Deploy] Updating .env from GitHub Secrets..."
  env_file=$(mktemp .env.deploy.XXXXXX)
  trap 'rm -f "$env_file"' EXIT
  printf '%s\n' "$DEPLOY_ENV_FILE" > "$env_file"
  mv "$env_file" .env
  trap - EXIT
fi

if [[ ! -f .env ]]; then
  echo "[Deploy] Missing .env. Configure it on this host or set the ENV_FILE GitHub secret." >&2
  exit 1
fi

docker info >/dev/null
docker compose config --quiet

# Use the Docker Engine's builder so both builds share its local image store.
BUILDX_BUILDER=$(docker context show)
export BUILDX_BUILDER
TEX_IMAGE=${TEX_IMAGE:-overbranch-texlive:2026.1}

if docker image inspect "$TEX_IMAGE" >/dev/null 2>&1; then
  echo "[Deploy] Reusing local TeX Live and fonts from $TEX_IMAGE."
else
  echo "[Deploy] Building $TEX_IMAGE with TeX Live and fonts for the first time on this host..."
  docker build -f docker/texlive.Dockerfile -t "$TEX_IMAGE" .
fi

echo "[Deploy] Building the application image..."
docker compose build --builder "$BUILDX_BUILDER" --build-arg "TEX_BASE=$TEX_IMAGE"

echo "[Deploy] Starting OverBranch and waiting for its health check..."
if ! docker compose up -d --no-build --pull never --wait --wait-timeout 120; then
  docker compose logs --tail=50
  exit 1
fi

docker compose ps

#!/bin/sh
# Entrypoint of the tex-runner sidecar (same image as the app; docker-compose.yml overrides the
# app's ENTRYPOINT with this). Warms the TeX caches, then becomes the HTTP server (PID 1 after
# exec, under compose's `init: true`, so SIGTERM reaches it and TeX children are reaped).
set -u

cd /app/backend

if [ "${TEX_RUNNER_WARMUP:-1}" != "0" ]; then
    python3 /app/docker/tex-runner-warmup.py || echo "tex-runner warm-up failed; starting cold"
fi

exec python3 -m tex_runner

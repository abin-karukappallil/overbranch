#!/bin/bash
set -e

echo "=========================================="
echo " Starting OverBranch TeX Engine & Web App"
echo "=========================================="

# Create uploads directory if missing
mkdir -p /app/uploads/projects

# Trap termination signals to cleanly shut down backend process on container exit
trap 'kill -TERM $BACKEND_PID 2>/dev/null' EXIT INT TERM

# Realtime collaboration rooms live in the worker process that owns the
# websocket, so two uvicorn workers would give two users two independent copies
# of the same document. Collaboration therefore pins the backend to one worker
# unless it is explicitly disabled (COLLAB_ENABLED=0) or a load balancer in
# front pins /ws/collab/<project_id> to one worker (COLLAB_MULTI_WORKER=1).
# The app is fully async and compiles already run in their own bounded thread
# pool, so a single worker is not the bottleneck it looks like.
BACKEND_WORKERS="${WORKERS:-2}"
if [ "${COLLAB_ENABLED:-1}" != "0" ] && [ "${COLLAB_MULTI_WORKER:-0}" != "1" ] && [ "$BACKEND_WORKERS" != "1" ]; then
    echo "► Realtime collaboration is enabled: pinning the backend to 1 worker"
    echo "  (was WORKERS=$BACKEND_WORKERS; set COLLAB_ENABLED=0 to keep multiple"
    echo "   workers, or COLLAB_MULTI_WORKER=1 if your proxy pins rooms by project)"
    BACKEND_WORKERS=1
fi

# Start Python FastAPI Backend on port 8000 in background
echo "► Starting FastAPI Backend (0.0.0.0:${BACKEND_PORT:-8000})..."
cd /app/backend
python3 -m uvicorn main:app \
    --host 0.0.0.0 \
    --port "${BACKEND_PORT:-8000}" \
    --workers "$BACKEND_WORKERS" \
    --timeout-keep-alive 65 \
    --timeout-graceful-shutdown 30 \
    --limit-concurrency 200 \
    --limit-max-requests 10000 &
BACKEND_PID=$!

# Wait for backend to initialize
sleep 2

# Start Next.js Web Application on port 3000 in foreground using Bun
echo "► Starting Next.js Web App with Bun (0.0.0.0:3000)..."
cd /app
export PORT=3000
export HOSTNAME="0.0.0.0"
exec bun run start

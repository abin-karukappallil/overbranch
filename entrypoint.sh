#!/bin/bash
set -e

echo "=========================================="
echo " Starting OverBranch TeX Engine & Web App"
echo "=========================================="

# Create uploads directory if missing
mkdir -p /app/uploads/projects

# Trap termination signals to cleanly shut down backend process on container exit
trap 'kill -TERM $BACKEND_PID 2>/dev/null' EXIT INT TERM

# Start Python FastAPI Backend on port 8000 in background
echo "► Starting FastAPI Backend (0.0.0.0:8000)..."
cd /app/backend
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Wait for backend to initialize
sleep 2

# Start Next.js Web Application on port 3000 in foreground
echo "► Starting Next.js Web App (0.0.0.0:3000)..."
cd /app
export PORT=3000
export HOSTNAME="0.0.0.0"
exec npm run start

#!/usr/bin/env bash
set -euo pipefail

export PORT="${PORT:-8080}"
export NODE_ENV="production"
export ML_SERVICE_URL="${ML_SERVICE_URL:-http://127.0.0.1:8001}"
export SKYGUARD_API_URL="${SKYGUARD_API_URL:-http://127.0.0.1:${PORT}/api}"

cleanup() {
  if [[ -n "${NODE_PID:-}" ]] && kill -0 "$NODE_PID" 2>/dev/null; then
    kill "$NODE_PID" 2>/dev/null || true
  fi
  if [[ -n "${ML_PID:-}" ]] && kill -0 "$ML_PID" 2>/dev/null; then
    kill "$ML_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

# Start the Node API first. The ML service performs an initial data refresh
# during FastAPI startup, so the API must already be reachable.
node --enable-source-maps artifacts/api-server/dist/index.mjs &
NODE_PID=$!

echo "SkyGuard API started with PID $NODE_PID on port $PORT"

# Wait for the API before starting ML. This avoids a startup race where the
# ML lifespan tries to fetch readings before the Node API is listening.
API_READY=0
for _ in {1..60}; do
  if curl -fsS "http://127.0.0.1:${PORT}/api/healthz" >/dev/null 2>&1; then
    API_READY=1
    break
  fi
  if ! kill -0 "$NODE_PID" 2>/dev/null; then
    echo "SkyGuard API exited before becoming ready" >&2
    exit 1
  fi
  sleep 1
done

if [[ "$API_READY" -ne 1 ]]; then
  echo "SkyGuard API did not become ready within 60 seconds" >&2
  exit 1
fi

echo "SkyGuard API is ready"

# Start the Python ML service only after the API is healthy.
python -m uvicorn app.main:app \
  --app-dir ml-service \
  --host 127.0.0.1 \
  --port 8001 \
  --log-level info &
ML_PID=$!

echo "SkyGuard ML service started with PID $ML_PID"

# Give ML time to initialize its model/baseline, then verify its health.
ML_READY=0
for _ in {1..60}; do
  if curl -fsS "${ML_SERVICE_URL}/health" >/dev/null 2>&1; then
    ML_READY=1
    break
  fi
  if ! kill -0 "$ML_PID" 2>/dev/null; then
    echo "SkyGuard ML service exited during startup" >&2
    exit 1
  fi
  sleep 1
done

if [[ "$ML_READY" -ne 1 ]]; then
  echo "SkyGuard ML service did not become ready within 60 seconds" >&2
  exit 1
fi

echo "SkyGuard ML service is ready"

# Keep the deployment alive while both services are running. If either
# process exits, terminate the other process and fail the deployment clearly.
while true; do
  if ! kill -0 "$NODE_PID" 2>/dev/null; then
    echo "SkyGuard API process stopped" >&2
    exit 1
  fi
  if ! kill -0 "$ML_PID" 2>/dev/null; then
    echo "SkyGuard ML process stopped" >&2
    exit 1
  fi
  sleep 5
done

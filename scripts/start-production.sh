#!/usr/bin/env bash
set -euo pipefail

export PORT="${PORT:-8080}"
export NODE_ENV="production"
export ML_SERVICE_URL="${ML_SERVICE_URL:-http://127.0.0.1:8001}"
export SKYGUARD_API_URL="${SKYGUARD_API_URL:-http://127.0.0.1:${PORT}/api}"

cleanup() {
  if [[ -n "${ML_PID:-}" ]] && kill -0 "$ML_PID" 2>/dev/null; then
    kill "$ML_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

python -m uvicorn app.main:app \
  --app-dir ml-service \
  --host 127.0.0.1 \
  --port 8001 \
  --log-level info &
ML_PID=$!

echo "SkyGuard ML service started with PID $ML_PID"
echo "SkyGuard API URL for ML: $SKYGUARD_API_URL"

node --enable-source-maps artifacts/api-server/dist/index.mjs &
NODE_PID=$!

wait "$NODE_PID"

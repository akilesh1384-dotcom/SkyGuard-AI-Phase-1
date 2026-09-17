#!/usr/bin/env bash
set -euo pipefail

# Build the Node application.
pnpm --filter @workspace/api-server run build

# Replit's deployment Python may not include pip. Bootstrap pip first,
# then install the ML service dependencies.
python -m ensurepip --upgrade
python -m pip install --no-cache-dir -r ml-service/requirements.txt

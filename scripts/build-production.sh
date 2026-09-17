#!/usr/bin/env bash
set -euo pipefail

# Build the Node application and install the Python ML runtime used by the
# published SkyGuard deployment. The production image already provides both
# Node.js and Python.
pnpm --filter @workspace/api-server run build
python -m pip install --no-cache-dir -r ml-service/requirements.txt

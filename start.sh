#!/usr/bin/env bash
set -euo pipefail

# Navigate to backend service
cd "$(dirname "$0")/backend"

# Ensure dependencies are installed (idempotent if already cached by build step)
if [ -f requirements.txt ]; then
  pip install --no-cache-dir -r requirements.txt
fi

# Start FastAPI with Uvicorn, honoring Railway-provided PORT
exec uvicorn src.main:app --host 0.0.0.0 --port "${PORT:-8000}"
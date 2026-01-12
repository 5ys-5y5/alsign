#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV_PATH="${PROJECT_ROOT}/.venv"
FRONTEND_DIST="${PROJECT_ROOT}/frontend/dist"

# Create virtual environment if it does not exist (build step should have created it already)
if [ ! -d "$VENV_PATH" ]; then
  python3 -m venv "$VENV_PATH"
fi

# Use virtualenv binaries first
export PATH="$VENV_PATH/bin:$PATH"

# Install backend deps only if uvicorn is missing (avoid slow runtime installs)
if ! command -v uvicorn >/dev/null 2>&1; then
  if [ -f "${PROJECT_ROOT}/backend/requirements.txt" ]; then
    pip install --no-cache-dir -r "${PROJECT_ROOT}/backend/requirements.txt"
  fi
fi

# Warn if frontend build output is missing; API can still run
if [ ! -f "${FRONTEND_DIST}/index.html" ]; then
  echo "Warning: frontend build output not found at ${FRONTEND_DIST}. Serving API only."
fi

# Navigate to backend service
cd "${PROJECT_ROOT}/backend"

# Start FastAPI with Uvicorn, honoring Railway-provided PORT
exec uvicorn src.main:app --host 0.0.0.0 --port "${PORT:-8000}"

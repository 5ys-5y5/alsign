#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV_PATH="${PROJECT_ROOT}/.venv"

# Create virtual environment if it does not exist (build step should have created it already)
if [ ! -d "$VENV_PATH" ]; then
  python3 -m venv "$VENV_PATH"
fi

# Use virtualenv binaries first
export PATH="$VENV_PATH/bin:$PATH"

# Navigate to backend service
cd "${PROJECT_ROOT}/backend"

# Ensure dependencies are installed (idempotent if already cached by build step)
if [ -f requirements.txt ]; then
  pip install --no-cache-dir -r requirements.txt
fi

# Start FastAPI with Uvicorn, honoring Railway-provided PORT
exec uvicorn src.main:app --host 0.0.0.0 --port "${PORT:-8000}"
#!/usr/bin/env bash
# start-backend.sh - Launcher for AEGIS FastAPI Backend Service (macOS / Linux)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

VENV_PYTHON="$PROJECT_ROOT/backend/.venv/bin/python"
if [ ! -f "$VENV_PYTHON" ]; then
    VENV_PYTHON="python3"
fi

# Ensure .env file exists
if [ ! -f ".env" ]; then
    echo "[WARN] .env missing. Copying from .env.example..."
    cp .env.example .env
fi

echo "========================================="
echo "     LAUNCHING AEGIS BACKEND DAEMON      "
echo "========================================="
echo "Root Path : $PROJECT_ROOT"
echo "Python    : $VENV_PYTHON"
echo "Endpoint  : http://127.0.0.1:8000"
echo "-----------------------------------------"

exec "$VENV_PYTHON" -m uvicorn backend.app.main:app \
    --host 127.0.0.1 \
    --port 8000 \
    --reload \
    --reload-dir backend \
    --reload-exclude "data*" \
    --reload-exclude "sandbox_runs*" \
    --reload-exclude "sandbox_runs_test*" \
    --reload-exclude "*/data/*" \
    --reload-exclude "*/data/**/*" \
    --reload-exclude "*/sandbox_runs/*" \
    --reload-exclude "*/sandbox_runs/**/*" \
    --reload-exclude "*/sandbox_runs_test/*" \
    --reload-exclude "*/sandbox_runs_test/**/*"


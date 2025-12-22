#!/bin/bash
set -e

# Make sure we are running in this script's directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Ensure venv exists
if [ ! -d ".venv" ]; then
  echo ">>> Creating venv..."
  python3 -m venv .venv
fi

source .venv/bin/activate

# Node version (for components/machinelearning/listen.mjs if you use it)
if command -v nvm >/dev/null 2>&1; then
  nvm use 18 || true
fi

export OPENCV_LOG_LEVEL=ERROR
export GST_DEBUG=0

python main.py "$@"

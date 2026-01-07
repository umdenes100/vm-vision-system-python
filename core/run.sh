#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${PROJECT_ROOT}/.venv"

source "${VENV_DIR}/bin/activate"

export PYTHONPATH="${PROJECT_ROOT}"

echo "[run] Starting vision system"
python "${PROJECT_ROOT}/core/main.py"

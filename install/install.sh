#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${PROJECT_ROOT}/.venv"

echo "[install] Project root: ${PROJECT_ROOT}"

# Create virtual environment if needed
if [ ! -d "${VENV_DIR}" ]; then
  echo "[install] Creating virtual environment"
  python3 -m venv "${VENV_DIR}"
else
  echo "[install] Virtual environment already exists"
fi

source "${VENV_DIR}/bin/activate"

echo "[install] Upgrading pip"
pip install --upgrade pip

echo "[install] Installing requirements"
pip install -r "${PROJECT_ROOT}/install/requirements.txt"

echo "[install] Done"

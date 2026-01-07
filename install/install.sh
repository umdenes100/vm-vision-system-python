#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${PROJECT_ROOT}/.venv"

echo "[install] Project root: ${PROJECT_ROOT}"

# ---- OS packages (Ubuntu/Debian) ----
if command -v apt-get >/dev/null 2>&1; then
  echo "[install] Installing OS packages (GStreamer + basics)..."
  sudo apt-get update
  sudo apt-get install -y \
    python3 python3-venv python3-pip \
    gstreamer1.0-tools \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav \
    ufw \
    lsof
else
  echo "[install] apt-get not found. Please install GStreamer and Python3 venv manually."
fi

# ---- Firewall rules (UFW if present) ----
if command -v ufw >/dev/null 2>&1; then
  echo "[install] Configuring firewall rules (ufw) if enabled..."
  # Only apply rules if ufw is enabled; otherwise skip (no side effects).
  if sudo ufw status | grep -q "Status: active"; then
    # Camera RTP/H264 over UDP
    sudo ufw allow 5000/udp || true
    # Web frontend
    sudo ufw allow 8080/tcp || true
    echo "[install] UFW rules ensured: 5000/udp and 8080/tcp"
  else
    echo "[install] UFW is installed but not active; skipping rule changes."
  fi
fi

# ---- Python venv ----
if [ ! -d "${VENV_DIR}" ]; then
  echo "[install] Creating virtual environment"
  python3 -m venv "${VENV_DIR}"
else
  echo "[install] Virtual environment already exists"
fi

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

echo "[install] Upgrading pip"
pip install --upgrade pip

echo "[install] Installing requirements"
pip install -r "${PROJECT_ROOT}/install/requirements.txt"

echo "[install] Done"

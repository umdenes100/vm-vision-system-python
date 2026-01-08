#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REQ_FILE="${ROOT_DIR}/install/requirements.txt"

echo "[install] Creating venv"
python3 -m venv "${ROOT_DIR}/.venv"
source "${ROOT_DIR}/.venv/bin/activate"

echo "[install] Upgrading pip"
python -m pip install --upgrade pip

echo "[install] Installing requirements"
python -m pip install -r "${REQ_FILE}"

echo "[install] Installing system deps (gstreamer + plugins)"
sudo apt-get update
sudo apt-get install -y \
  gstreamer1.0-tools \
  gstreamer1.0-plugins-base \
  gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-bad \
  gstreamer1.0-plugins-ugly \
  gstreamer1.0-libav

echo "[install] Firewall rules (ufw) - allowing web + esp ws + udp camera"
if command -v ufw >/dev/null 2>&1; then
  sudo ufw allow 8080/tcp || true
  sudo ufw allow 7755/tcp || true
  sudo ufw allow 5000/udp || true
else
  echo "[install] ufw not found, skipping firewall configuration"
fi

echo "[install] Done"

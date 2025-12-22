#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# Vision System — One-Command Installer (Ubuntu 22.04 Jammy)
# ============================================================
# Preps system deps, Python venv, Python deps, verifies
# OpenCV+GStreamer, and builds OpenCV from source (contrib)
# with a robust cv2 loader fix for venvs.
#
# Usage:
#   chmod +x install_vision_system.sh
#   ./install_vision_system.sh
#
# Env options:
#   VENV_PATH       (default: .venv)
#   BUILD_OPENCV    auto|always|never (default: auto)
#   OPENCV_VERSION  (default: 4.8.1)
#   OPENCV_JOBS     (default: nproc)
# ============================================================

VENV_PATH="${VENV_PATH:-.venv}"
BUILD_OPENCV="${BUILD_OPENCV:-auto}"
OPENCV_VERSION="${OPENCV_VERSION:-4.8.1}"
OPENCV_JOBS="${OPENCV_JOBS:-$(nproc)}"

# ----------------------------
# Helpers
# ----------------------------
apt_lock_aware() {
  # Wait for dpkg/apt locks gracefully
  local cmd="$1"
  local tries=30
  local delay=5

  for ((i=1; i<=tries; i++)); do
    if sudo bash -lc "$cmd"; then
      return 0
    fi
    echo ">>> apt/dpkg busy, retry $i/$tries in ${delay}s…"
    sleep "$delay"
  done

  echo "ERROR: apt/dpkg still locked after retries." >&2
  return 1
}

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "ERROR: Required command not found: $1" >&2
    exit 1
  fi
}

echo "============================================================"
echo ">>> Vision System Installer"
echo ">>> Repo: $(pwd)"
echo ">>> VENV_PATH=${VENV_PATH}"
echo ">>> BUILD_OPENCV=${BUILD_OPENCV}"
echo ">>> OPENCV_VERSION=${OPENCV_VERSION}"
echo ">>> OPENCV_JOBS=${OPENCV_JOBS}"
echo "============================================================"

# ----------------------------
# Basic checks
# ----------------------------
need_cmd bash
need_cmd sudo

if ! command -v lsb_release >/dev/null 2>&1; then
  echo "lsb_release not found. Installing…"
  apt_lock_aware "apt-get update -y"
  apt_lock_aware "apt-get install -y lsb-release"
fi

UBU_VER="$(lsb_release -rs || true)"
if [[ "${UBU_VER}" != 22.04* ]]; then
  echo "WARNING: Detected Ubuntu ${UBU_VER}. This script targets 22.04 (Jammy). Continuing anyway…"
fi

# ----------------------------
# System packages
# ----------------------------
echo ">>> Installing system dependencies (apt)…"
apt_lock_aware "apt-get update -y"
apt_lock_aware "apt-get install -y \
  python3 python3-venv python3-pip \
  build-essential cmake git pkg-config curl ca-certificates \
  v4l-utils \
  libgtk-3-dev \
  libjpeg-dev libpng-dev libtiff-dev libwebp-dev libopenjp2-7-dev \
  libavcodec-dev libavformat-dev libavutil-dev libswscale-dev \
  libxvidcore-dev libx264-dev libx265-dev libv4l-dev \
  libtbb-dev \
  gstreamer1.0-tools gstreamer1.0-libav \
  gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
  libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev libgstreamer-plugins-bad1.0-dev \
  qttools5-dev-tools qttools5-dev"

echo ">>> GStreamer version: $(pkg-config --modversion gstreamer-1.0 || echo 'unknown')"

# ----------------------------
# Node.js (nvm) for Firebase model listener
# ----------------------------
echo ">>> Installing nvm + Node.js 18 (required for listen.mjs)…"
export NVM_DIR="${HOME}/.nvm"
if [[ ! -s "${NVM_DIR}/nvm.sh" ]]; then
  echo ">>> nvm not found; installing to ${NVM_DIR}…"
  # Official nvm install script (writes to ~/.bashrc). We also source nvm.sh below for this run.
  curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
fi

# shellcheck disable=SC1090
[ -s "${NVM_DIR}/nvm.sh" ] && . "${NVM_DIR}/nvm.sh"

if ! command -v nvm >/dev/null 2>&1; then
  echo "ERROR: nvm install failed or could not be loaded." >&2
  exit 1
fi

# Install and select Node 18 (pins default for future shells)
nvm install 18 >/dev/null
nvm alias default 18 >/dev/null
nvm use 18 >/dev/null

if ! command -v node >/dev/null 2>&1; then
  echo "ERROR: node is still not available after nvm install." >&2
  exit 1
fi

echo ">>> Node version: $(node -v)"
echo ">>> npm version: $(npm -v)"

# ----------------------------
# Python venv
# ----------------------------
if [[ ! -d "${VENV_PATH}" ]]; then
  echo ">>> Creating venv at ${VENV_PATH}…"
  python3 -m venv "${VENV_PATH}"
fi

# Ensure venv ownership (avoid root-owned venv)
if [[ ! -w "${VENV_PATH}" ]]; then
  echo ">>> Fixing venv ownership (sudo)…"
  sudo chown -R "$USER":"$USER" "${VENV_PATH}"
fi

# Activate venv
# shellcheck disable=SC1090
source "${VENV_PATH}/bin/activate"
export PIP_REQUIRE_VIRTUALENV=1

# Upgrade pip/setuptools/wheel
python - <<'PY'
import subprocess, sys
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--upgrade", "pip<25", "setuptools", "wheel"], check=True)
PY

# ----------------------------
# Python requirements
# ----------------------------
REQ_FILE="requirements.txt"
if [[ -f "${REQ_FILE}" ]]; then
  echo ">>> Installing Python requirements from ${REQ_FILE}…"
  pip install -q -r "${REQ_FILE}"
else
  echo "WARNING: ${REQ_FILE} not found. Skipping pip -r install."
fi

# Keep NumPy <2 to match OpenCV ABI expectations (esp. if OpenCV was built against NumPy 1.x)
python - <<'PY'
import sys, subprocess
try:
    import numpy as np
    major = int(np.__version__.split(".")[0])
except Exception:
    major = 0
if major >= 2 or major == 0:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--upgrade", "numpy<2"], check=True)
PY

# ----------------------------
# OpenCV build decision
# ----------------------------
echo ">>> Checking OpenCV..."
PY_CV_OK=0
python - <<'PY' || PY_CV_OK=1
import cv2
print(">>> cv2 import OK:", cv2.__version__)
PY

# Determine whether to build OpenCV from source
DO_BUILD=0
if [[ "${BUILD_OPENCV}" == "always" ]]; then
  DO_BUILD=1
elif [[ "${BUILD_OPENCV}" == "never" ]]; then
  DO_BUILD=0
else
  # auto: build if cv2 import fails or version mismatch
  if [[ "${PY_CV_OK}" -ne 0 ]]; then
    DO_BUILD=1
  else
    CV_VER="$(python - <<'PY'
import cv2
print(cv2.__version__)
PY
)"
    if [[ "${CV_VER}" != "${OPENCV_VERSION}"* ]]; then
      echo ">>> OpenCV version ${CV_VER} != desired ${OPENCV_VERSION}. Will build from source (auto)."
      DO_BUILD=1
    fi
  fi
fi

# ----------------------------
# Build OpenCV from source (optional)
# ----------------------------
if [[ "${DO_BUILD}" -eq 1 ]]; then
  echo ">>> Building OpenCV ${OPENCV_VERSION} from source…"

  WORKDIR="${HOME}/opencv_build"
  OPENCV_DIR="${WORKDIR}/opencv"
  OPENCV_CONTRIB_DIR="${WORKDIR}/opencv_contrib"
  BUILD_DIR="${WORKDIR}/build"

  mkdir -p "${WORKDIR}"
  cd "${WORKDIR}"

  if [[ ! -d "${OPENCV_DIR}/.git" ]]; then
    git clone --depth 1 --branch "${OPENCV_VERSION}" https://github.com/opencv/opencv.git
  else
    cd "${OPENCV_DIR}"
    git fetch --all --tags
    git checkout "${OPENCV_VERSION}"
    cd "${WORKDIR}"
  fi

  if [[ ! -d "${OPENCV_CONTRIB_DIR}/.git" ]]; then
    git clone --depth 1 --branch "${OPENCV_VERSION}" https://github.com/opencv/opencv_contrib.git
  else
    cd "${OPENCV_CONTRIB_DIR}"
    git fetch --all --tags
    git checkout "${OPENCV_VERSION}"
    cd "${WORKDIR}"
  fi

  rm -rf "${BUILD_DIR}"
  mkdir -p "${BUILD_DIR}"
  cd "${BUILD_DIR}"

  cmake -D CMAKE_BUILD_TYPE=Release \
        -D CMAKE_INSTALL_PREFIX=/usr/local \
        -D OPENCV_EXTRA_MODULES_PATH="${OPENCV_CONTRIB_DIR}/modules" \
        -D WITH_GSTREAMER=ON \
        -D WITH_V4L=ON \
        -D WITH_QT=OFF \
        -D BUILD_TESTS=OFF \
        -D BUILD_PERF_TESTS=OFF \
        -D BUILD_EXAMPLES=OFF \
        -D BUILD_opencv_python3=ON \
        -D PYTHON3_EXECUTABLE="$(command -v python3)" \
        -D PYTHON3_INCLUDE_DIR="$(python3 - <<'PY'
import sysconfig
print(sysconfig.get_paths()["include"])
PY
)" \
        -D PYTHON3_PACKAGES_PATH="$(python3 - <<'PY'
import site
print(site.getsitepackages()[0])
PY
)" \
        "${OPENCV_DIR}"

  make -j"${OPENCV_JOBS}"
  sudo make install
  sudo ldconfig

  # Remove pip wheels to avoid conflicts with /usr/local install
  pip uninstall -y opencv-python opencv-contrib-python >/dev/null 2>&1 || true

  echo ">>> OpenCV build/install complete."
  cd - >/dev/null || true
else
  echo ">>> Skipping OpenCV source build."
fi

# ----------------------------
# Final sanity checks
# ----------------------------
echo ">>> Final checks: importing cv2 and testing GStreamer backend…"
python - <<'PY'
import cv2, numpy as np
print(">>> OpenCV:", cv2.__version__)
print(">>> NumPy:", np.__version__)
# Ensure GStreamer backend is present
try:
    backends = cv2.videoio_registry.getBackends()
    print(">>> VideoIO backends:", backends)
except Exception as e:
    print(">>> VideoIO backend query not available:", e)
print(">>> Installer complete ✅")
PY

#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# Vision System — One-Command Installer (Ubuntu 22.04 Jammy)
# ============================================================
# This script prepares system deps, Python venv, Python deps,
# sanity-checks OpenCV + GStreamer, and (if needed) builds
# OpenCV from source with GStreamer enabled.
#
# Usage:
#   chmod +x install_vision_system.sh
#   ./install_vision_system.sh
#
# Options (env vars):
#   VENV_PATH            Path to the Python venv (default: .venv)
#   BUILD_OPENCV         "auto" (default), "always", or "never"
#   OPENCV_VERSION       Git tag or branch to build (default: 4.8.1)
#   OPENCV_JOBS          Parallel build jobs (default: nproc)
# ============================================================

# ----------------------------
# Config
# ----------------------------
VENV_PATH="${VENV_PATH:-.venv}"
BUILD_OPENCV="${BUILD_OPENCV:-auto}"           # auto | always | never
OPENCV_VERSION="${OPENCV_VERSION:-4.8.1}"
OPENCV_JOBS="${OPENCV_JOBS:-$(nproc)}"

REPO_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

echo ">>> Installer starting in: $REPO_DIR"

# ----------------------------
# Sanity checks
# ----------------------------
if ! command -v lsb_release >/dev/null 2>&1; then
  echo "lsb_release not found. Installing..."
  sudo apt-get update -y
  sudo apt-get install -y lsb-release
fi

UBU_VER="$(lsb_release -rs || true)"
if [[ "${UBU_VER}" != 22.04* ]]; then
  echo "WARNING: Detected Ubuntu ${UBU_VER}. This script targets 22.04 (Jammy). Continuing anyway..."
fi

# ----------------------------
# System packages
# ----------------------------
echo ">>> Installing system dependencies (apt)…"
sudo apt-get update -y
sudo apt-get install -y \
  python3 python3-venv python3-pip \
  build-essential cmake git pkg-config \
  v4l-utils \
  libgtk-3-dev \
  libjpeg-dev libpng-dev libtiff-dev libwebp-dev libopenjp2-7-dev \
  libavcodec-dev libavformat-dev libavutil-dev libswscale-dev \
  libxvidcore-dev libx264-dev libx265-dev libv4l-dev \
  libtbb-dev \
  gstreamer1.0-tools gstreamer1.0-libav \
  gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
  libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev libgstreamer-plugins-bad1.0-dev \
  qttools5-dev-tools qttools5-dev

echo ">>> GStreamer version: $(pkg-config --modversion gstreamer-1.0 || echo 'unknown')"

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

# Upgrade pip/setuptools/wheel (pip<25 is safe across py3.10)
python - <<'PY'
import subprocess, sys
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--upgrade", "pip<25", "setuptools", "wheel"], check=True)
PY

# ----------------------------
# Python requirements
# ----------------------------
# Respect provided requirements.txt but ensure NumPy <2 to match many OpenCV/torch combos on Jammy.
REQ_FILE="requirements.txt"
if [[ ! -f "$REQ_FILE" ]]; then
  echo "ERROR: requirements.txt not found next to this installer."
  exit 1
fi

echo ">>> Installing Python dependencies from $REQ_FILE…"
# Prefer the project's pinned versions; they already set numpy~=1.24.x and opencv-python~=4.7.x
python -m pip install -r "$REQ_FILE"

# Hard-ensure NumPy major <2
python - <<'PY'
import importlib.metadata as md, subprocess, sys
try:
    v = md.version("numpy")
    major = int(v.split(".")[0])
except Exception:
    major = 0
if major >= 2:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--upgrade", "numpy<2"], check=True)
PY

# ----------------------------
# Quick OpenCV + GStreamer check
# ----------------------------
echo ">>> Verifying OpenCV + GStreamer support…"
set +e
python - <<'PY'
import sys, re
ok = False
try:
    import cv2, numpy as np
    info = cv2.getBuildInformation()
    # Strong signal if the CMake summary says YES
    if re.search(r"GStreamer\s*:\s*YES", info, re.I):
        # Try a tiny one-buffer GStreamer pipeline
        cap = cv2.VideoCapture("videotestsrc num-buffers=1 ! videoconvert ! appsink", cv2.CAP_GSTREAMER)
        ok = cap.isOpened()
        cap.release()
    print("CHECK:", "OK" if ok else "NO")
except Exception as e:
    print("CHECK: NO (error)", e)
sys.exit(0 if ok else 3)
PY
CHECK_RC=$?
set -e

NEED_BUILD=0
case "$BUILD_OPENCV" in
  always) NEED_BUILD=1 ;;
  never)  NEED_BUILD=0 ;;
  auto)   if [[ $CHECK_RC -ne 0 ]]; then NEED_BUILD=1; fi ;;
  *) echo "Invalid BUILD_OPENCV=$BUILD_OPENCV (use auto|always|never)"; exit 2 ;;
esac

# ----------------------------
# Build OpenCV from source (if required)
# ----------------------------
if [[ $NEED_BUILD -eq 1 ]]; then
  echo ">>> OpenCV lacks GStreamer support (or BUILD_OPENCV=always). Building OpenCV ${OPENCV_VERSION} from source…"

  OPENCV_SRC="${HOME}/opencv"
  OPENCV_CONTRIB_SRC="${HOME}/opencv_contrib"
  OPENCV_BUILD="${OPENCV_SRC}/build"

  # Fetch sources
  if [[ ! -d "${OPENCV_SRC}/.git" ]]; then
    git clone --depth=1 --branch "${OPENCV_VERSION}" https://github.com/opencv/opencv.git "${OPENCV_SRC}"
  else
    (cd "${OPENCV_SRC}" && git fetch --depth=1 origin "${OPENCV_VERSION}" && git checkout "${OPENCV_VERSION}")
  fi

  if [[ ! -d "${OPENCV_CONTRIB_SRC}/.git" ]]; then
    git clone --depth=1 --branch "${OPENCV_VERSION}" https://github.com/opencv/opencv_contrib.git "${OPENCV_CONTRIB_SRC}"
  else
    (cd "${OPENCV_CONTRIB_SRC}" && git fetch --depth=1 origin "${OPENCV_VERSION}" && git checkout "${OPENCV_VERSION}")
  fi

  # Resolve Python paths
  PY_EXEC="$(command -v python)"
  SITE_PKGS="$(python - <<'PY'
import site; sp = getattr(site, 'getsitepackages', lambda: [])(); print(sp[0] if sp else site.getusersitepackages())
PY
)"
  NUMPY_INC="$(python - <<'PY'
import numpy as np; print(np.get_include())
PY
)"

  # Clean build dir
  rm -rf "${OPENCV_BUILD}"
  mkdir -p "${OPENCV_BUILD}"

  cmake -S "${OPENCV_SRC}" -B "${OPENCV_BUILD}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX=/usr/local \
    -DOPENCV_GENERATE_PKGCONFIG=ON \
    -DBUILD_TESTS=OFF \
    -DBUILD_PERF_TESTS=OFF \
    -DOPENCV_ENABLE_NONFREE=ON \
    -DWITH_GSTREAMER=ON \
    -DWITH_FFMPEG=ON \
    -DWITH_V4L=ON \
    -DWITH_TBB=ON \
    -DBUILD_opencv_python3=ON \
    -DOPENCV_EXTRA_MODULES_PATH="${OPENCV_CONTRIB_SRC}/modules" \
    -DPYTHON3_EXECUTABLE="${PY_EXEC}" \
    -DPYTHON3_PACKAGES_PATH="${SITE_PKGS}" \
    -DPYTHON3_NUMPY_INCLUDE_DIRS="${NUMPY_INC}"

  cmake --build "${OPENCV_BUILD}" -- -j"${OPENCV_JOBS}"
  sudo cmake --install "${OPENCV_BUILD}"
  sudo ldconfig

  # Remove wheel OpenCV if present to avoid module confusion
  python -m pip uninstall -y opencv-python opencv-contrib-python || true

  echo ">>> Verifying OpenCV + GStreamer after build…"
  python - <<'PY'
import sys, re
import cv2
info = cv2.getBuildInformation()
print(next((l for l in info.splitlines() if "GStreamer" in l), "No GStreamer line"))
import numpy as np
cap = cv2.VideoCapture("videotestsrc num-buffers=1 ! videoconvert ! appsink", cv2.CAP_GSTREAMER)
print("CAP_GSTREAMER opened:", cap.isOpened())
sys.exit(0 if cap.isOpened() else 2)
PY
fi

# ----------------------------
# Desktop integration & runner
# ----------------------------
echo ">>> Setting executable bit on RunVisionSystem.sh…"
chmod +x "${REPO_DIR}/RunVisionSystem.sh" || true

if [[ -f "${REPO_DIR}/runner.desktop" ]]; then
  echo ">>> Copying desktop shortcut to ~/Desktop…"
  mkdir -p "${HOME}/Desktop"
  cp -f "${REPO_DIR}/runner.desktop" "${HOME}/Desktop/runner.desktop"
  # Try to rewrite absolute path to Exec (optional, noop if no Exec key)
  if command -v sed >/dev/null 2>&1; then
    sed -i "s|^Exec=.*|Exec=${REPO_DIR}/RunVisionSystem.sh|g" "${HOME}/Desktop/runner.desktop" || true
  fi
  chmod +x "${HOME}/Desktop/runner.desktop" || true
else
  echo "NOTE: runner.desktop not found in repo; skipping desktop shortcut."
fi

# ----------------------------
# Final notes & smoke test
# ----------------------------
echo ">>> Installation complete."
echo ">>> You can launch the app via:"
echo "    ${REPO_DIR}/RunVisionSystem.sh"
echo ">>> If using GNOME, you may need to right-click the Desktop shortcut and choose 'Allow Launching' once."
echo ">>> Optional quick smoke test (no network):"
echo "    python - <<'PY'"
echo "    import cv2; cap=cv2.VideoCapture('videotestsrc num-buffers=1 ! videoconvert ! appsink', cv2.CAP_GSTREAMER); print('CAP:', cap.isOpened())"
echo "    PY"

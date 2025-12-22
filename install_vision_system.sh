#!/usr/bin/env bash
set -euo pipefail

VENV_PATH="${VENV_PATH:-.venv}"
BUILD_OPENCV="${BUILD_OPENCV:-auto}"   # auto|always|never
OPENCV_VERSION="${OPENCV_VERSION:-4.8.1}"
OPENCV_JOBS="${OPENCV_JOBS:-$(nproc)}"

apt_lock_aware() {
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

need_cmd bash
need_cmd sudo

echo ">>> Installing system dependencies (apt)…"
apt_lock_aware "apt-get update -y"
apt_lock_aware "apt-get install -y \
  python3 python3-venv python3-pip \
  build-essential cmake git pkg-config curl ca-certificates \
  libjpeg-dev libpng-dev libtiff-dev libwebp-dev libopenjp2-7-dev \
  libavcodec-dev libavformat-dev libavutil-dev libswscale-dev \
  libxvidcore-dev libx264-dev libx265-dev libv4l-dev \
  libtbb-dev \
  gstreamer1.0-tools gstreamer1.0-libav \
  gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
  libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev libgstreamer-plugins-bad1.0-dev"

echo ">>> Installing nvm + Node.js 18 (required for listen.mjs)…"
export NVM_DIR="${HOME}/.nvm"
if [[ ! -s "${NVM_DIR}/nvm.sh" ]]; then
  curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
fi
# shellcheck disable=SC1090
[ -s "${NVM_DIR}/nvm.sh" ] && . "${NVM_DIR}/nvm.sh"
if ! command -v nvm >/dev/null 2>&1; then
  echo "ERROR: nvm install failed or could not be loaded." >&2
  exit 1
fi
nvm install 18 >/dev/null
nvm alias default 18 >/dev/null
nvm use 18 >/dev/null
command -v node >/dev/null 2>&1 || { echo "ERROR: node not available after nvm install." >&2; exit 1; }
echo ">>> Node: $(node -v), npm: $(npm -v)"

echo ">>> Creating/activating venv..."
if [[ ! -d "${VENV_PATH}" ]]; then
  python3 -m venv "${VENV_PATH}"
fi
if [[ ! -w "${VENV_PATH}" ]]; then
  sudo chown -R "$USER":"$USER" "${VENV_PATH}"
fi
# shellcheck disable=SC1090
source "${VENV_PATH}/bin/activate"
export PIP_REQUIRE_VIRTUALENV=1

python - <<'PY'
import subprocess, sys
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--upgrade", "pip<25", "setuptools", "wheel"], check=True)
PY

if [[ -f requirements.txt ]]; then
  echo ">>> Installing Python requirements..."
  pip install -q -r requirements.txt
fi

# Keep NumPy <2 (ABI friendliness with many OpenCV builds)
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

echo ">>> Checking cv2 import..."
PY_CV_OK=0
python - <<'PY' || PY_CV_OK=1
import cv2
print(">>> cv2 imported from:", cv2.__file__)
print(">>> cv2 version:", cv2.__version__)
PY

DO_BUILD=0
if [[ "${BUILD_OPENCV}" == "always" ]]; then
  DO_BUILD=1
elif [[ "${BUILD_OPENCV}" == "never" ]]; then
  DO_BUILD=0
else
  if [[ "${PY_CV_OK}" -ne 0 ]]; then
    DO_BUILD=1
  else
    CV_VER="$(python - <<'PY'
import cv2
print(cv2.__version__)
PY
)"
    if [[ "${CV_VER}" != "${OPENCV_VERSION}"* ]]; then
      DO_BUILD=1
    fi
  fi
fi

if [[ "${DO_BUILD}" -ne 1 ]]; then
  echo ">>> Skipping OpenCV source build."
  echo ">>> Installer complete ✅"
  exit 0
fi

echo ">>> Building OpenCV ${OPENCV_VERSION} from source (with correct Python install path)…"

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

# IMPORTANT: Use the venv python and install cv2 into the venv site-packages
PY_EXE="$(python -c 'import sys; print(sys.executable)')"
PY_SITE="$(python -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"

echo ">>> Using Python executable: ${PY_EXE}"
echo ">>> Installing OpenCV Python bindings to: ${PY_SITE}"

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
      -D PYTHON3_EXECUTABLE="${PY_EXE}" \
      -D OPENCV_PYTHON3_INSTALL_PATH="${PY_SITE}" \
      "${OPENCV_DIR}"

make -j"${OPENCV_JOBS}"
sudo make install
sudo ldconfig

# Remove pip wheels to avoid shadowing
pip uninstall -y opencv-python opencv-contrib-python >/dev/null 2>&1 || true
pip uninstall -y cv2 >/dev/null 2>&1 || true

echo ">>> OpenCV build/install complete."

echo ">>> Final checks: importing cv2..."
python - <<'PY'
import cv2
print(">>> cv2 imported from:", getattr(cv2, "__file__", "<no __file__>"))
print(">>> cv2 has __version__?:", hasattr(cv2, "__version__"))
print(">>> cv2 version:", getattr(cv2, "__version__", "<missing>"))
PY

echo ">>> Installer complete ✅"

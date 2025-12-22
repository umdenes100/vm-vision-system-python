#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# Vision System — One-Command Installer (Ubuntu 22.04 Jammy)
# ============================================================
# Adds: nvm + Node.js 18 + npm deps for Firebase model listener
# Keeps: your working OpenCV/cv2 loader logic intact
# ============================================================

VENV_PATH="${VENV_PATH:-.venv}"
BUILD_OPENCV="${BUILD_OPENCV:-auto}"
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

if ! command -v lsb_release >/dev/null 2>&1; then
  echo "lsb_release not found. Installing…"
  apt_lock_aware "apt-get update -y"
  apt_lock_aware "apt-get install -y lsb-release"
fi

UBU_VER="$(lsb_release -rs || true)"
if [[ "${UBU_VER}" != 22.04* ]]; then
  echo "WARNING: Detected Ubuntu ${UBU_VER}. This script targets 22.04 (Jammy). Continuing anyway…"
fi

echo ">>> Installing system dependencies (apt)…"
apt_lock_aware "apt-get update -y"
apt_lock_aware "apt-get install -y \
  python3 python3-venv python3-pip \
  build-essential cmake git pkg-config \
  curl ca-certificates \
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
# Node.js (nvm) + npm deps for Firebase listener
# ----------------------------
echo ">>> Installing nvm + Node.js 18 (required for listen.mjs)…"
export NVM_DIR="${HOME}/.nvm"
if [[ ! -s "${NVM_DIR}/nvm.sh" ]]; then
  echo ">>> nvm not found; installing…"
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

if ! command -v node >/dev/null 2>&1; then
  echo "ERROR: node is still not available after nvm install." >&2
  exit 1
fi
echo ">>> Node version: $(node -v)"
echo ">>> npm version: $(npm -v)"

echo ">>> Installing npm dependencies for Firebase listener…"
if [[ -f "components/machinelearning/package.json" ]]; then
  pushd "components/machinelearning" >/dev/null
  npm install --silent
  popd >/dev/null
else
  echo "ERROR: components/machinelearning/package.json not found. Cannot install Firebase deps." >&2
  exit 1
fi

# ----------------------------
# Python venv
# ----------------------------
if [[ ! -d "${VENV_PATH}" ]]; then
  echo ">>> Creating venv at ${VENV_PATH}…"
  python3 -m venv "${VENV_PATH}"
fi

if [[ ! -w "${VENV_PATH}" ]]; then
  echo ">>> Fixing venv ownership (sudo)…"
  sudo chown -R "$USER":"$USER" "${VENV_PATH}"
fi

# shellcheck disable=SC1090
source "${VENV_PATH}/bin/activate"
export PIP_REQUIRE_VIRTUALENV=1

python - <<'PY'
import subprocess, sys
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--upgrade", "pip<25", "setuptools", "wheel"], check=True)
PY

REQ_FILE="requirements.txt"
if [[ -f "${REQ_FILE}" ]]; then
  echo ">>> Installing Python requirements from ${REQ_FILE}…"
  pip install -q -r "${REQ_FILE}"
else
  echo "WARNING: ${REQ_FILE} not found. Skipping pip -r install."
fi

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

  pip uninstall -y opencv-python opencv-contrib-python >/dev/null 2>&1 || true

  echo ">>> OpenCV build/install complete."
  cd - >/dev/null || true
else
  echo ">>> Skipping OpenCV source build."
fi

# ----------------------------
# Robust cv2 loader fix for venvs (kept as-is, but with safe import)
# ----------------------------
python - <<'PY'
import os, sys, site, pathlib, textwrap

# This was previously an unconditional import that can fail on clean machines.
try:
    import stream_promises_fix  # noqa: F401
except Exception:
    pass

def write_loader(cv2_pkg: pathlib.Path):
    init_py = cv2_pkg / "__init__.py"
    if init_py.exists():
        return
    code = textwrap.dedent("""
    # Auto-generated cv2 loader to avoid namespace-package imports when cv2 is installed via OpenCV build.
    import importlib.util as _iu
    from pathlib import Path as _Path

    _pkg_dir = _Path(__file__).resolve().parent
    _so = None

    for _p in _pkg_dir.rglob("cv2*.so"):
        _so = _p
        break

    if _so is None:
        raise ImportError(f"cv2 loader could not find cv2*.so under {_pkg_dir}")

    _spec = _iu.spec_from_file_location("cv2", str(_so))
    if _spec is None or _spec.loader is None:
        raise ImportError(f"cv2 loader could not load spec for {_so}")

    _mod = _iu.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)  # type: ignore[attr-defined]
    globals().update(_mod.__dict__)
    """).lstrip()
    init_py.write_text(code)
    print(">>> Wrote cv2/__init__.py loader:", init_py)

def ensure_cv2_loader():
    purelib = site.getsitepackages()[0]
    cv2_pkg = pathlib.Path(purelib) / "cv2"
    cv2_pkg.mkdir(parents=True, exist_ok=True)
    write_loader(cv2_pkg)

def test_cv2():
    import cv2
    print(">>> cv2 imported from:", getattr(cv2, "__file__", None))
    print(">>> cv2 has __version__?:", hasattr(cv2, "__version__"))
    print(">>> cv2 version:", getattr(cv2, "__version__", "<missing>"))

def ensure_gstreamer():
    import cv2
    cap = cv2.VideoCapture('videotestsrc num-buffers=1 ! videoconvert ! appsink', cv2.CAP_GSTREAMER)
    ok = bool(cap.isOpened())
    cap.release()
    print(">>> CAP_GSTREAMER opened:", ok)

ensure_cv2_loader()
test_cv2()
ensure_gstreamer()
PY

echo ">>> Installer complete ✅"
